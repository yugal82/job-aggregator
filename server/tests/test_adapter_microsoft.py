"""MicrosoftAdapter tests — fetches a GitHub-hosted scraper mirror and
parses the ``{jobs: [...]}`` payload. No detail-fetch phase (the scraper
doesn't capture descriptions, so canonical.description stays None)."""
import json
from pathlib import Path

import httpx
import pytest

from app.adapters.http import HTTPClient
from app.adapters.microsoft import MicrosoftAdapter

JOBS_FIXTURE = Path(__file__).parent / "fixtures/adapters/microsoft/jobs.json"


def _payload() -> dict:
    return json.loads(JOBS_FIXTURE.read_text())


def _adapter(http: HTTPClient, config: dict | None = None) -> MicrosoftAdapter:
    return MicrosoftAdapter(
        http=http,
        config=config or {"url": "https://raw.githubusercontent.com/yugal82/msft-jobs/main/jobs.json"},
        company_slug="microsoft",
    )


def _handler_from(payload: dict):
    def inner(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)
    return inner


async def test_discover_fetches_configured_url() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=_payload())

    http = HTTPClient(
        base_url="",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    try:
        raws = await _adapter(http).discover()
    finally:
        await http.close()

    assert len(seen) == 1
    assert seen[0].endswith("/yugal82/msft-jobs/main/jobs.json")
    assert len(raws) == 3


async def test_normalize_uses_standardized_location_split() -> None:
    """Standardized location "Redmond, WA, US" splits cleanly into
    city/state/country; the verbose fallback format is NOT split (its
    components come in a different order)."""
    http = HTTPClient(
        base_url="",
        transport=httpx.MockTransport(_handler_from(_payload())),
        rate_limit_per_second=0,
    )
    try:
        adapter = _adapter(http)
        raws = await adapter.discover()
    finally:
        await http.close()

    first = adapter.normalize(raws[0])
    assert first.company_slug == "microsoft"
    assert first.source_provider == "microsoft-careers"
    assert first.title.startswith("Software Engineer")
    primary = first.locations[0]
    assert primary.city == "Redmond"
    assert primary.state == "WA"
    assert primary.country == "US"


async def test_source_url_prefixes_position_url_with_host() -> None:
    http = HTTPClient(
        base_url="",
        transport=httpx.MockTransport(_handler_from(_payload())),
        rate_limit_per_second=0,
    )
    try:
        adapter = _adapter(http)
        raws = await adapter.discover()
    finally:
        await http.close()

    canonical = adapter.normalize(raws[0])
    assert canonical.source_url
    assert canonical.source_url.startswith("https://jobs.careers.microsoft.com/")


async def test_posted_at_parsed_from_epoch_seconds() -> None:
    """``postedTs`` ships as a unix-seconds integer — must land as a
    tz-aware UTC datetime."""
    http = HTTPClient(
        base_url="",
        transport=httpx.MockTransport(_handler_from(_payload())),
        rate_limit_per_second=0,
    )
    try:
        adapter = _adapter(http)
        raws = await adapter.discover()
    finally:
        await http.close()

    canonical = adapter.normalize(raws[0])
    assert canonical.posted_at is not None
    assert canonical.posted_at.tzinfo is not None


async def test_remote_work_option_sets_remote_allowed() -> None:
    """A manually-crafted entry with workLocationOption=remote must flip
    the remote_allowed flag on every parsed location row."""
    payload = {
        "last_updated": "2026-10-15T00:00:00Z",
        "total_jobs": 1,
        "jobs": [
            {
                "id": 42,
                "displayJobId": "900001",
                "name": "Remote Software Engineer",
                "standardizedLocations": ["Redmond, WA, US"],
                "locations": ["United States, Washington, Redmond"],
                "postedTs": 1792000000,
                "workLocationOption": "remote",
                "atsJobId": "900001",
                "positionUrl": "/careers/job/42",
                "department": "Software Engineering",
            }
        ],
    }
    http = HTTPClient(
        base_url="",
        transport=httpx.MockTransport(_handler_from(payload)),
        rate_limit_per_second=0,
    )
    try:
        adapter = _adapter(http)
        raws = await adapter.discover()
    finally:
        await http.close()

    canonical = adapter.normalize(raws[0])
    assert canonical.workplace_type == "Remote"
    for loc in canonical.locations:
        assert loc.remote_allowed is True


async def test_multiple_standardized_locations_each_get_a_row() -> None:
    """The 'Customer Experience Engineer' fixture has 8 standardized
    locations — every unique one becomes a CanonicalLocation."""
    http = HTTPClient(
        base_url="",
        transport=httpx.MockTransport(_handler_from(_payload())),
        rate_limit_per_second=0,
    )
    try:
        adapter = _adapter(http)
        raws = await adapter.discover()
    finally:
        await http.close()

    many = next(c for c in (adapter.normalize(r) for r in raws) if len(c.locations) >= 5)
    for loc in many.locations:
        assert loc.country == "US"


async def test_missing_description_is_null_not_crash() -> None:
    """Scraper doesn't capture descriptions; adapter must set None rather
    than raising or defaulting to empty-string."""
    http = HTTPClient(
        base_url="",
        transport=httpx.MockTransport(_handler_from(_payload())),
        rate_limit_per_second=0,
    )
    try:
        adapter = _adapter(http)
        raws = await adapter.discover()
    finally:
        await http.close()

    for r in raws:
        canonical = adapter.normalize(r)
        assert canonical.description is None


async def test_requisition_id_prefers_ats_job_id() -> None:
    http = HTTPClient(
        base_url="",
        transport=httpx.MockTransport(_handler_from(_payload())),
        rate_limit_per_second=0,
    )
    try:
        adapter = _adapter(http)
        raws = await adapter.discover()
    finally:
        await http.close()

    canonical = adapter.normalize(raws[0])
    assert canonical.requisition_id


async def test_malformed_response_raises_clear_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    http = HTTPClient(
        base_url="",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    try:
        with pytest.raises(ValueError, match="jobs"):
            await _adapter(http).discover()
    finally:
        await http.close()


async def test_level_passes_through_to_canonical_level() -> None:
    """The scraper's `level` (or legacy `ic_level`) is normalized and
    surfaces as `canonical.level` for downstream `?level=` filtering."""
    levels = [
        ("level", "IC2"),
        ("ic_level", "IC 3"),       # legacy field name, space variant
        (None, None),               # field missing entirely
        ("level", "IC3 / ic-4"),    # range → each part canonicalized
        ("level", "Intern"),        # non-IC band passes through
        ("level", "   "),           # blank → None
    ]
    jobs = []
    for i, (key, value) in enumerate(levels):
        job = {
            "id": i, "displayJobId": f"J{i}", "name": f"SWE {i}",
            "standardizedLocations": ["Redmond, WA, US"],
            "postedTs": 1792000000, "workLocationOption": "onsite",
            "atsJobId": f"J{i}", "positionUrl": f"/careers/job/{i}",
            "department": "Eng",
        }
        if key:
            job[key] = value
        jobs.append(job)

    http = HTTPClient(
        base_url="",
        transport=httpx.MockTransport(_handler_from({"jobs": jobs})),
        rate_limit_per_second=0,
    )
    try:
        adapter = _adapter(http)
        raws = await adapter.discover()
    finally:
        await http.close()

    assert [adapter.normalize(r).level for r in raws] == [
        "IC2", "IC3", None, "IC3/IC4", "Intern", None,
    ]


async def test_default_url_used_when_config_omits_it() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"jobs": []})

    http = HTTPClient(
        base_url="",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    adapter = MicrosoftAdapter(http=http, config={}, company_slug="microsoft")
    try:
        await adapter.discover()
    finally:
        await http.close()

    assert seen[0] == MicrosoftAdapter._DEFAULT_URL
