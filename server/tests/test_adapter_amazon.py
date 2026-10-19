import json
from pathlib import Path

import httpx

from app.adapters.amazon import AmazonAdapter
from app.adapters.http import HTTPClient

FIXTURE = Path(__file__).parent / "fixtures/adapters/amazon/sample.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def _adapter(http: HTTPClient) -> AmazonAdapter:
    return AmazonAdapter(http=http, config={}, company_slug="amazon")


async def test_discover_hits_search_endpoint_and_paginates_to_stop() -> None:
    """Paginator should stop as soon as a page returns fewer rows than page size."""
    seen_offsets: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/en/search.json"
        seen_offsets.append(int(request.url.params["offset"]))
        return httpx.Response(200, json=_fixture())

    http = HTTPClient(
        base_url="https://www.amazon.jobs",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    try:
        raws = await _adapter(http).discover()
    finally:
        await http.close()

    # 2 jobs returned, _PAGE_SIZE=100 → one call, no further pages.
    assert seen_offsets == [0]
    assert len(raws) == 2
    assert raws[0].source_job_id == "10568469"
    assert raws[0].source_url == "https://www.amazon.jobs/en/jobs/10568469/software-dev-engineer-ii-sde2-amazon-connect"


async def test_normalize_merges_text_blocks_and_parses_locations() -> None:
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
    assert canonical.company_slug == "amazon"
    assert canonical.source_provider == "amazon-careers"
    assert canonical.department == "Software Development"
    assert canonical.team == "team-sde-primary"
    assert canonical.employment_type == "Full-time"
    # Description must include all three text parts
    assert canonical.description and "Amazon Connect" in canonical.description
    assert canonical.description and "distributed systems" in canonical.description
    assert canonical.description and "AWS familiarity" in canonical.description
    # Locations: list-of-json-strings parsed into two entries, Santa Clara + NY
    assert len(canonical.locations) == 2
    states = {loc.state for loc in canonical.locations}
    assert states == {"NY", "CA"}
    assert all(loc.country == "US" for loc in canonical.locations)


async def test_normalize_detects_virtual_as_remote() -> None:
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

    virtual_job = adapter.normalize(raws[1])
    assert len(virtual_job.locations) == 1
    assert virtual_job.locations[0].remote_allowed is True


async def test_posted_date_double_space_parses() -> None:
    """Amazon's `posted_date` often has a double space before single-digit days."""
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

    assert raws[0].posted_at is not None
    # "October  3, 2026"
    assert raws[0].posted_at.year == 2026
    assert raws[0].posted_at.month == 10
    assert raws[0].posted_at.day == 3


async def test_discover_sends_configured_filters() -> None:
    recorded: dict[str, list[str]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        # httpx URL.params returns str → list[str] for repeated keys
        for key in request.url.params.keys():
            recorded[key] = request.url.params.get_list(key)
        return httpx.Response(200, json={"jobs": []})

    http = HTTPClient(
        base_url="https://mock",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    adapter = AmazonAdapter(
        http=http,
        config={
            "filters": {
                "category[]": "software-development",
                "normalized_country_code[]": "USA",
                "sort": "recent",
            }
        },
        company_slug="amazon",
    )
    try:
        await adapter.discover()
    finally:
        await http.close()

    assert "software-development" in recorded["category[]"]
    assert "USA" in recorded["normalized_country_code[]"]
