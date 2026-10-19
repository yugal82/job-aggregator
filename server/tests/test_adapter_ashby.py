import json
from decimal import Decimal
from pathlib import Path

import httpx

from app.adapters.ashby import AshbyAdapter
from app.adapters.http import HTTPClient

FIXTURE = Path(__file__).parent / "fixtures/adapters/ashby/sample.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def _adapter(http: HTTPClient) -> AshbyAdapter:
    return AshbyAdapter(
        http=http,
        config={"job_board_name": "anthropic"},
        company_slug="anthropic",
    )


async def test_discover_uses_post_and_filters_unlisted() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.method)
        assert request.url.path == "/posting-api/job-board/anthropic"
        assert request.url.params["includeCompensation"] == "true"
        return httpx.Response(200, json=_fixture())

    http = HTTPClient(
        base_url="https://api.ashbyhq.com",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    try:
        raws = await _adapter(http).discover()
    finally:
        await http.close()

    assert seen == ["POST"]
    # 3 in fixture, one has isListed=false and should be dropped.
    assert len(raws) == 2
    ids = {r.source_job_id for r in raws}
    assert ids == {"job_01H", "job_02R"}


async def test_normalize_produces_expected_canonical_with_salary() -> None:
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

    canonical = next(c for r in raws if (c := adapter.normalize(r)).source_job_id == "job_01H")
    assert canonical.department == "Research"
    assert canonical.team == "Alignment"
    assert canonical.employment_type == "Full-time"
    assert canonical.salary_min == Decimal("300000")
    assert canonical.salary_max == Decimal("400000")
    assert canonical.salary_currency == "USD"
    assert canonical.description and "alignment research" in canonical.description
    assert len(canonical.locations) == 2  # primary + one secondary


async def test_normalize_isremote_flag_sets_workplace_type() -> None:
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

    remote_job = next(
        c for r in raws if (c := adapter.normalize(r)).source_job_id == "job_02R"
    )
    assert remote_job.workplace_type == "Remote"
    assert remote_job.locations[0].remote_allowed is True
    # No compensation block on this job → nulls
    assert remote_job.salary_min is None


async def test_missing_org_raises() -> None:
    import pytest

    adapter = AshbyAdapter(http=None, config={}, company_slug="anthropic")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="job_board_name"):
        adapter._org()
