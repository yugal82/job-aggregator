import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.adapters.greenhouse import GreenhouseAdapter
from app.adapters.http import HTTPClient

FIXTURE = Path(__file__).parent / "fixtures/adapters/greenhouse/sample.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def _adapter(http: HTTPClient) -> GreenhouseAdapter:
    return GreenhouseAdapter(http=http, config={"board_token": "stripe"}, company_slug="stripe")


async def test_discover_parses_board_response() -> None:
    payload = _fixture()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/boards/stripe/jobs"
        assert request.url.params["content"] == "true"
        return httpx.Response(200, json=payload)

    http = HTTPClient(
        base_url="https://boards-api.greenhouse.io",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    try:
        raw_jobs = await _adapter(http).discover()
    finally:
        await http.close()

    assert len(raw_jobs) == 2
    first = raw_jobs[0]
    assert first.source_job_id == "4567890"
    assert first.title == "Software Engineer, Payments"
    assert first.source_url == "https://boards.greenhouse.io/stripe/jobs/4567890"
    assert first.location_text == "San Francisco, CA"
    assert first.updated_at == datetime(2026, 9, 1, 12, 34, 56, tzinfo=timezone.utc)


async def test_normalize_produces_expected_canonical() -> None:
    http = HTTPClient(
        base_url="https://mock",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=_fixture())),
        rate_limit_per_second=0,
    )
    try:
        adapter = _adapter(http)
        raw_jobs = await adapter.discover()
    finally:
        await http.close()

    canonical = adapter.normalize(raw_jobs[0])

    assert canonical.company_slug == "stripe"
    assert canonical.source_provider == "greenhouse"
    assert canonical.source_job_id == "4567890"
    assert canonical.title == "Software Engineer, Payments"
    assert canonical.description is not None
    assert "Build payment systems." in canonical.description
    assert "Python" in canonical.description
    assert canonical.department == "Engineering"
    assert canonical.team == "Payments"
    assert canonical.employment_type == "Full-time"
    assert canonical.workplace_type == "On-site"
    assert canonical.requisition_id == "REQ-1001"
    assert canonical.application_url == "https://boards.greenhouse.io/stripe/jobs/4567890"
    assert len(canonical.locations) == 1
    assert canonical.locations[0].location_text == "San Francisco, CA"
    assert canonical.locations[0].remote_allowed is False
    assert len(canonical.content_hash) == 64  # sha256 hex


async def test_normalize_flags_remote_location() -> None:
    http = HTTPClient(
        base_url="https://mock",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=_fixture())),
        rate_limit_per_second=0,
    )
    try:
        adapter = _adapter(http)
        raw_jobs = await adapter.discover()
    finally:
        await http.close()

    remote_job = adapter.normalize(raw_jobs[1])
    assert remote_job.locations[0].remote_allowed is True
    assert remote_job.requisition_id is None


def test_missing_board_token_raises() -> None:
    import pytest

    from app.adapters.greenhouse import GreenhouseAdapter as _GA

    adapter = _GA(http=None, config={}, company_slug="stripe")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="board_token"):
        adapter._board_token()


def test_sanitize_requisition_id_rejects_placeholders() -> None:
    from app.adapters.greenhouse import _sanitize_requisition_id

    assert _sanitize_requisition_id(None) is None
    assert _sanitize_requisition_id("") is None
    assert _sanitize_requisition_id("  ") is None
    # placeholder text — companies put natural language in this field
    assert _sanitize_requisition_id("See Opening ID") is None
    assert _sanitize_requisition_id("N/A - see description") is None
    # real reqs — short opaque tokens with no whitespace
    assert _sanitize_requisition_id("REQ-1001") == "REQ-1001"
    assert _sanitize_requisition_id("R100") == "R100"
    assert _sanitize_requisition_id("  REQ-2  ") == "REQ-2"
