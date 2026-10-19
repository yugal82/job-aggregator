import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.adapters.http import HTTPClient
from app.adapters.lever import LeverAdapter

FIXTURE = Path(__file__).parent / "fixtures/adapters/lever/sample.json"


def _fixture() -> list:
    return json.loads(FIXTURE.read_text())


def _adapter(http: HTTPClient) -> LeverAdapter:
    return LeverAdapter(http=http, config={"site": "netflix"}, company_slug="netflix")


async def test_discover_hits_expected_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v0/postings/netflix"
        assert request.url.params["mode"] == "json"
        return httpx.Response(200, json=_fixture())

    http = HTTPClient(
        base_url="https://api.lever.co",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    try:
        raw = await _adapter(http).discover()
    finally:
        await http.close()

    assert len(raw) == 2
    first = raw[0]
    assert first.source_job_id == "abc-123"
    assert first.title == "Senior Backend Engineer"
    assert first.location_text == "Remote - US"
    # 1725186400000 ms → 2024-09-01T09:46:40Z
    assert first.updated_at == datetime.fromtimestamp(1725186400.0, tz=timezone.utc)


async def test_normalize_produces_expected_canonical() -> None:
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
    assert canonical.source_provider == "lever"
    assert canonical.department == "Engineering"
    assert canonical.team == "Payments"
    assert canonical.employment_type == "Full-time"
    assert canonical.workplace_type == "Remote"
    assert canonical.requisition_id == "REQ-42"
    assert canonical.description and "reliable systems" in canonical.description
    assert canonical.description and "distributed systems" in canonical.description
    # allLocations produced 2 CanonicalLocations; workplaceType=remote flags them all
    assert len(canonical.locations) == 2
    assert all(loc.remote_allowed for loc in canonical.locations)


async def test_normalize_hybrid_workplace_flag() -> None:
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

    hybrid_job = adapter.normalize(raws[1])
    assert hybrid_job.workplace_type == "Hybrid"
    assert hybrid_job.team is None
    assert hybrid_job.requisition_id is None
    assert len(hybrid_job.locations) == 1
    assert hybrid_job.locations[0].hybrid_allowed is True


async def test_missing_site_raises() -> None:
    import pytest

    adapter = LeverAdapter(http=None, config={}, company_slug="netflix")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="site"):
        adapter._site()
