import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.adapters.http import HTTPClient
from app.adapters.netflix import NetflixAdapter

FIXTURE = Path(__file__).parent / "fixtures/adapters/netflix/sample.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def _adapter(http: HTTPClient) -> NetflixAdapter:
    return NetflixAdapter(http=http, config={}, company_slug="netflix")


async def test_discover_uses_v2_apply_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/apply/v2/jobs"
        assert request.url.params["domain"] == "netflix.com"
        return httpx.Response(200, json=_fixture())

    http = HTTPClient(
        base_url="https://explore.jobs.netflix.net",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    try:
        raws = await _adapter(http).discover()
    finally:
        await http.close()

    assert len(raws) == 2
    assert raws[0].source_job_id == "790298014263"
    # t_update=1779148800 → 2026-05-18 UTC
    assert raws[0].updated_at == datetime.fromtimestamp(1779148800, tz=timezone.utc)


async def test_normalize_strips_html_and_sets_remote_workplace() -> None:
    http = HTTPClient(
        base_url="https://mock",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=_fixture())),
        rate_limit_per_second=0,
    )
    try:
        adapter = _adapter(http)
        raws = await adapter.discover()
    finally:
        await http.close()

    canonical = adapter.normalize(raws[0])
    assert canonical.company_slug == "netflix"
    assert canonical.source_provider == "netflix-careers"
    assert canonical.workplace_type == "Remote"
    assert canonical.department == "Data & Insights"
    assert canonical.team == "Streaming"
    assert canonical.description and "AI foundation" in canonical.description
    # requisition_id falls back to ats_job_id
    assert canonical.requisition_id == "AJRT30201"
    # Single location, flagged remote via work_location_option
    assert len(canonical.locations) == 1
    assert canonical.locations[0].remote_allowed is True


async def test_normalize_onsite_leaves_remote_flag_false() -> None:
    http = HTTPClient(
        base_url="https://mock",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=_fixture())),
        rate_limit_per_second=0,
    )
    try:
        adapter = _adapter(http)
        raws = await adapter.discover()
    finally:
        await http.close()

    onsite = adapter.normalize(raws[1])
    assert onsite.workplace_type == "On-site"
    assert onsite.locations[0].remote_allowed is False
    assert onsite.locations[0].hybrid_allowed is False


async def test_pagination_follows_count_even_when_pages_are_small() -> None:
    """Netflix caps `num` server-side (ignores higher values). Pagination must
    rely on the `count` field (or an empty page) rather than ``len < page_size``.
    """
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["start"])
        calls.append(start)
        total = 25  # pretend Netflix has 25 jobs
        page_size = 10  # server-side cap, less than our request
        remaining = max(0, total - start)
        rows = min(page_size, remaining)
        return httpx.Response(
            200,
            json={
                "count": total,
                "positions": [
                    {
                        "id": start + i,
                        "name": f"Job {start + i}",
                        "location": "Remote, United States",
                        "locations": ["Remote, United States"],
                        "canonicalPositionUrl": f"https://example/job/{start + i}",
                        "t_create": 1721000000,
                        "t_update": 1721000000,
                        "work_location_option": "remote",
                        "job_description": "<p>Build things.</p>",
                    }
                    for i in range(rows)
                ],
            },
        )

    http = HTTPClient(
        base_url="https://mock",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    try:
        raws = await _adapter(http).discover()
    finally:
        await http.close()

    assert len(raws) == 25
    assert calls == [0, 10, 20]  # three pages, stopped once start >= count


async def test_custom_domain_from_config() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["domain"])
        return httpx.Response(200, json={"positions": [], "count": 0})

    http = HTTPClient(
        base_url="https://mock",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    adapter = NetflixAdapter(
        http=http, config={"domain": "other.example"}, company_slug="netflix"
    )
    try:
        await adapter.discover()
    finally:
        await http.close()

    assert seen == ["other.example"]
