import json
from pathlib import Path

import httpx
import pytest

from app.adapters.http import HTTPClient
from app.adapters.workday import WorkdayAdapter

SEARCH_FIXTURE = Path(__file__).parent / "fixtures/adapters/workday/search.json"
DETAIL_FIXTURE = Path(__file__).parent / "fixtures/adapters/workday/detail.json"

NVIDIA_CONFIG = {
    "host": "nvidia.wd5.myworkdayjobs.com",
    "tenant": "nvidia",
    "site": "NVIDIAExternalCareerSite",
}


def _search() -> dict:
    return json.loads(SEARCH_FIXTURE.read_text())


def _detail() -> dict:
    return json.loads(DETAIL_FIXTURE.read_text())


def _adapter(http: HTTPClient, config: dict | None = None) -> WorkdayAdapter:
    return WorkdayAdapter(
        http=http, config=config or NVIDIA_CONFIG, company_slug="nvidia"
    )


def _handler(detail: dict | None):
    def inner(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/jobs") and request.method == "POST":
            return httpx.Response(200, json=_search())
        if "/job/" in path and request.method == "GET":
            if detail is None:
                return httpx.Response(404, text="not found")
            return httpx.Response(200, json=detail)
        return httpx.Response(500, text=f"unexpected {request.method} {path}")

    return inner


async def test_discover_hits_full_absolute_url_with_tenant_and_site() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        if request.url.path.endswith("/jobs"):
            return httpx.Response(200, json=_search())
        return httpx.Response(200, json=_detail())

    http = HTTPClient(
        base_url="", transport=httpx.MockTransport(handler), rate_limit_per_second=0
    )
    try:
        raws = await _adapter(http).discover()
    finally:
        await http.close()

    # The first request should be a POST to the tenant-specific jobs endpoint.
    assert seen_urls[0].endswith(
        "nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs"
    )
    # Two postings → two detail fetches.
    detail_calls = [u for u in seen_urls if "/job/" in u]
    assert len(detail_calls) == 2
    assert len(raws) == 2


async def test_list_request_body_includes_applied_facets() -> None:
    captured_body: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/jobs") and request.method == "POST":
            nonlocal_body = json.loads(request.content.decode())
            captured_body.update(nonlocal_body)
            return httpx.Response(200, json=_search())
        return httpx.Response(200, json=_detail())

    http = HTTPClient(
        base_url="", transport=httpx.MockTransport(handler), rate_limit_per_second=0
    )
    adapter = _adapter(
        http,
        {**NVIDIA_CONFIG, "applied_facets": {"locationCountry": ["US-id"]}},
    )
    try:
        await adapter.discover()
    finally:
        await http.close()

    assert captured_body["appliedFacets"] == {"locationCountry": ["US-id"]}
    assert captured_body["offset"] == 0
    assert captured_body["limit"] == WorkdayAdapter._PAGE_SIZE


async def test_normalize_parses_description_and_multi_location() -> None:
    http = HTTPClient(
        base_url="", transport=httpx.MockTransport(_handler(_detail())),
        rate_limit_per_second=0,
    )
    try:
        adapter = _adapter(http)
        raws = await adapter.discover()
    finally:
        await http.close()

    canonical = adapter.normalize(raws[0])
    assert canonical.company_slug == "nvidia"
    assert canonical.source_provider == "workday"
    assert canonical.source_job_id == "JR2023850"
    assert canonical.employment_type == "Full-time"
    assert canonical.description and "synthetic data pipelines" in canonical.description
    assert canonical.requisition_id == "JR2023850"
    # 1 primary + 3 additional locations
    assert len(canonical.locations) == 4
    loc_texts = {loc.location_text for loc in canonical.locations}
    assert "US, CA, Santa Clara" in loc_texts
    # Remote locations get flagged
    remote_count = sum(1 for loc in canonical.locations if loc.remote_allowed)
    assert remote_count == 3


async def test_pagination_stops_at_total() -> None:
    """Workday pages return `total`; stop once we've consumed that many."""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/jobs") and request.method == "POST":
            body = json.loads(request.content.decode())
            offset = body["offset"]
            calls.append(offset)
            total = 45  # pretend 45 roles, page size 20 → 3 pages
            remaining = max(0, total - offset)
            page_size = min(20, remaining)
            return httpx.Response(
                200,
                json={
                    "total": total,
                    "jobPostings": [
                        {
                            "title": f"Role {offset + i}",
                            "externalPath": f"/job/path_{offset + i}",
                            "locationsText": "US",
                            "postedOn": "Today",
                            "bulletFields": [f"JR{offset + i:05d}"],
                        }
                        for i in range(page_size)
                    ],
                },
            )
        # Detail — return minimal valid payload so the adapter doesn't choke
        return httpx.Response(
            200,
            json={
                "jobPostingInfo": {
                    "title": "Role",
                    "location": "US",
                    "jobDescription": "",
                    "jobReqId": "JR00000",
                    "timeType": "Full time",
                    "startDate": "2026-10-01",
                    "externalUrl": "https://example/job",
                }
            },
        )

    http = HTTPClient(
        base_url="", transport=httpx.MockTransport(handler), rate_limit_per_second=0
    )
    try:
        raws = await _adapter(http).discover()
    finally:
        await http.close()

    assert calls == [0, 20, 40]
    assert len(raws) == 45


async def test_detail_404_falls_back_without_description() -> None:
    http = HTTPClient(
        base_url="", transport=httpx.MockTransport(_handler(detail=None)),
        rate_limit_per_second=0,
    )
    try:
        adapter = _adapter(http)
        raws = await adapter.discover()
    finally:
        await http.close()

    # Still 2 raws, but each lacks detail info
    assert len(raws) == 2
    canonical = adapter.normalize(raws[0])
    # req_id fell back to the list record's bulletFields
    assert canonical.source_job_id == "JR2023850"
    # No detail → no description, no additionalLocations
    assert canonical.description is None
    # Primary location falls back to the list's locationsText
    assert canonical.locations and canonical.locations[0].location_text == "5 Locations"


def test_missing_config_raises() -> None:
    adapter = WorkdayAdapter(http=None, config={}, company_slug="nvidia")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="host/tenant/site"):
        adapter._coords()
