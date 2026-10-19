"""AtlassianAdapter tests — hits the public JSON proxy and parses its
flat-array response. All job data arrives inline on the listings call; no
detail-fetch phase exists."""
import json
from pathlib import Path

import httpx
import pytest

from app.adapters.atlassian import AtlassianAdapter
from app.adapters.http import HTTPClient

LISTINGS_FIXTURE = Path(__file__).parent / "fixtures/adapters/atlassian/listings.json"


def _listings() -> list[dict]:
    return json.loads(LISTINGS_FIXTURE.read_text())


def _adapter(http: HTTPClient) -> AtlassianAdapter:
    return AtlassianAdapter(http=http, config={}, company_slug="atlassian")


def _handler_from(listings: list[dict]):
    def inner(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/endpoint/careers/listings":
            return httpx.Response(200, json=listings)
        return httpx.Response(500, text=f"unexpected {request.method} {request.url.path}")
    return inner


async def test_discover_hits_listings_endpoint() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=_listings())

    http = HTTPClient(
        base_url="https://www.atlassian.com",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    try:
        raws = await _adapter(http).discover()
    finally:
        await http.close()

    assert len(seen) == 1
    assert seen[0].endswith("/endpoint/careers/listings")
    assert len(raws) == 3


async def test_normalize_us_job_sets_country_and_remote() -> None:
    http = HTTPClient(
        base_url="https://www.atlassian.com",
        transport=httpx.MockTransport(_handler_from(_listings())),
        rate_limit_per_second=0,
    )
    try:
        adapter = _adapter(http)
        raws = await adapter.discover()
    finally:
        await http.close()

    # First fixture job: "Data Engineer Intern, 2027 Summer U.S."
    us_job = next(r for r in raws if "Summer U.S." in r.title or "United States" in (r.location_text or ""))
    canonical = adapter.normalize(us_job)

    assert canonical.company_slug == "atlassian"
    assert canonical.source_provider == "atlassian-careers"
    # `type` is sometimes null (seen on intern rows); when present it maps.
    assert canonical.employment_type in {None, "Full-time", "Part-time", "Internship"}
    assert canonical.description
    # Primary location is a US one — country should populate from parsing.
    primary = canonical.locations[0]
    assert primary.country == "United States"
    # "Remote - Remote" alt location in the fixture → remote_allowed on at least one row
    remote_rows = [loc for loc in canonical.locations if loc.remote_allowed]
    assert remote_rows, "expected at least one remote-flagged location"


async def test_normalize_non_us_job_sets_correct_country() -> None:
    http = HTTPClient(
        base_url="https://www.atlassian.com",
        transport=httpx.MockTransport(_handler_from(_listings())),
        rate_limit_per_second=0,
    )
    try:
        adapter = _adapter(http)
        raws = await adapter.discover()
    finally:
        await http.close()

    india_job = next(r for r in raws if "India" in (r.location_text or ""))
    canonical = adapter.normalize(india_job)

    primary = canonical.locations[0]
    assert primary.country == "India"
    # "Bengaluru" → city
    assert primary.city == "Bengaluru"


async def test_remote_only_location_leaves_country_none() -> None:
    """A pure "Remote - Remote" string has no country token — the parser
    must not invent one."""
    custom = [
        {
            "id": 9999,
            "portalJobPost": {
                "portalId": 17,
                "portalUrl": "https://globalcareers-atlassian.icims.com/jobs/9999",
                "id": 9999,
                "updatedDate": "2026-10-01 12:00 PM",
            },
            "title": "Senior Software Engineer",
            "type": "Full-Time",
            "locations": ["Remote - Remote"],
            "category": "Engineering",
            "overview": "<p>Build things.</p>",
            "applyUrl": "https://globalcareers-atlassian.icims.com/jobs/9999/apply",
        }
    ]
    http = HTTPClient(
        base_url="https://www.atlassian.com",
        transport=httpx.MockTransport(_handler_from(custom)),
        rate_limit_per_second=0,
    )
    try:
        adapter = _adapter(http)
        raws = await adapter.discover()
    finally:
        await http.close()

    canonical = adapter.normalize(raws[0])
    assert len(canonical.locations) == 1
    assert canonical.locations[0].country is None
    assert canonical.locations[0].remote_allowed is True


async def test_updated_date_is_parsed() -> None:
    http = HTTPClient(
        base_url="https://www.atlassian.com",
        transport=httpx.MockTransport(_handler_from(_listings())),
        rate_limit_per_second=0,
    )
    try:
        adapter = _adapter(http)
        raws = await adapter.discover()
    finally:
        await http.close()

    canonical = adapter.normalize(raws[0])
    # All fixture jobs have an updatedDate — posted_at must land as a datetime.
    assert canonical.posted_at is not None
    assert canonical.posted_at.year >= 2024


async def test_source_url_prefers_portal_url_over_apply_url() -> None:
    custom = [
        {
            "id": 42,
            "portalJobPost": {
                "portalId": 17,
                "portalUrl": "https://globalcareers-atlassian.icims.com/jobs/42/role/job",
                "id": 42,
                "updatedDate": "2026-10-01 12:00 PM",
            },
            "title": "Engineer",
            "type": "Full-Time",
            "locations": ["San Francisco - United States - Remote"],
            "category": "Engineering",
            "overview": "<p>Short.</p>",
            "applyUrl": "https://globalcareers-atlassian.icims.com/jobs/42/role/job?mode=apply",
        }
    ]
    http = HTTPClient(
        base_url="https://www.atlassian.com",
        transport=httpx.MockTransport(_handler_from(custom)),
        rate_limit_per_second=0,
    )
    try:
        adapter = _adapter(http)
        raws = await adapter.discover()
    finally:
        await http.close()

    canonical = adapter.normalize(raws[0])
    # source_url (the browseable page) comes from portalUrl, not apply URL.
    assert canonical.source_url and "mode=apply" not in canonical.source_url
    # application_url retains the apply query string.
    assert canonical.application_url and "mode=apply" in canonical.application_url


async def test_unexpected_response_type_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "object"})

    http = HTTPClient(
        base_url="https://www.atlassian.com",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    try:
        with pytest.raises(ValueError, match="expected list"):
            await _adapter(http).discover()
    finally:
        await http.close()
