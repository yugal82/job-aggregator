"""AppleAdapter tests — hits jobs.apple.com, decodes the embedded
``window.__staticRouterHydrationData`` blob, and normalizes without a
detail fetch. Fixtures capture the real HTML response shape so a parser
regression breaks CI before touching production traffic."""
import json
from pathlib import Path

import httpx
import pytest

from app.adapters.apple import (
    AppleAdapter,
    _extract_hydration,
)
from app.adapters.http import HTTPClient

PAGE_FIXTURE = Path(__file__).parent / "fixtures/adapters/apple/search_page_1.html"


@pytest.fixture(autouse=True)
def _no_empty_page_delay(monkeypatch):
    monkeypatch.setattr(AppleAdapter, "_EMPTY_RETRY_DELAY_SECONDS", 0.0)


def _empty_page_html() -> str:
    payload = {"loaderData": {"search": {"searchResults": [], "totalRecords": 0}}}
    escaped = json.dumps(json.dumps(payload))
    return f'<script>window.__staticRouterHydrationData = JSON.parse({escaped})</script>'


def _page_html() -> str:
    return PAGE_FIXTURE.read_text()


def _adapter(http: HTTPClient, config: dict | None = None) -> AppleAdapter:
    return AppleAdapter(
        http=http, config=config or {}, company_slug="apple"
    )


def _handler_from_pages(pages: list[str]):
    """Return a Mock transport that serves successive pages. Any extra
    requests return a 200 with an empty searchResults list via the last
    page."""
    count = {"n": 0}

    def inner(request: httpx.Request) -> httpx.Response:
        idx = count["n"]
        count["n"] += 1
        if idx < len(pages):
            return httpx.Response(200, text=pages[idx])
        # tail: return a page with zero results so pagination stops
        return httpx.Response(
            200,
            text='<html><script>window.__staticRouterHydrationData = '
                 'JSON.parse("' + json.dumps(json.dumps({"loaderData":{"search":{"searchResults":[], "totalRecords": 0}}})).strip('"') + '")</script></html>'
        )

    return inner


async def test_extract_hydration_round_trip() -> None:
    """Fixture HTML must decode into a well-formed hydration tree with
    the expected top-level shape."""
    doc = _extract_hydration(_page_html())
    search = doc["loaderData"]["search"]
    assert isinstance(search["searchResults"], list)
    assert search["searchResults"]
    assert isinstance(search["totalRecords"], int)


async def test_discover_parses_fixture_page() -> None:
    http = HTTPClient(
        base_url="https://jobs.apple.com",
        transport=httpx.MockTransport(_handler_from_pages([_page_html()])),
        rate_limit_per_second=0,
    )
    try:
        raws = await _adapter(http).discover()
    finally:
        await http.close()

    # Fixture has 20 search results, but managedPipelineRole rows get filtered.
    # Lower-bound: at least 10 real postings survive.
    assert len(raws) >= 10
    first = raws[0]
    assert first.source_job_id, "positionId must become source_job_id"
    assert first.title
    assert first.source_url and first.source_url.startswith("https://jobs.apple.com/en-us/details/")


async def test_pagination_hits_sequential_pages() -> None:
    """Each discover() call should walk ``?page=N`` until the hydration
    returns fewer than _PAGE_SIZE results or we reach totalRecords."""
    seen_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        seen_pages.append(page)
        # First two pages: full page of 20 results. Third page: empty.
        if page <= 2:
            results = [
                {
                    "positionId": f"{page}00{i}",
                    "postingTitle": f"Role {page}-{i}",
                    "locations": [{"name": "Austin", "countryName": "United States of America"}],
                    "team": {"teamName": "Software", "teamCode": "SFTWR"},
                    "homeOffice": False,
                    "managedPipelineRole": False,
                    "standardWeeklyHours": "40",
                    "postingDate": 1700000000000,
                    "postDateInGMT": "Thu, 23 Nov 2023 00:00:00 GMT",
                    "reqId": f"{page}00{i}-REQ",
                    "jobSummary": "<p>Build.</p>",
                }
                for i in range(20)
            ]
            total = 45
        else:
            results = []
            total = 45
        page_data = {
            "loaderData": {
                "search": {
                    "searchResults": results,
                    "totalRecords": total,
                    "queryParams": {"page": str(page)},
                }
            }
        }
        payload = json.dumps(page_data)
        escaped = json.dumps(payload)  # outer encode so it fits inside JSON.parse("...")
        html = f'<html><script>window.__staticRouterHydrationData = JSON.parse({escaped})</script></html>'
        return httpx.Response(200, text=html)

    http = HTTPClient(
        base_url="https://jobs.apple.com",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    try:
        raws = await _adapter(http).discover()
    finally:
        await http.close()

    # Three pages fetched (2 full + 1 empty terminator).
    assert seen_pages == [1, 2, 3]
    assert len(raws) == 40  # 20 + 20 from the two full pages


async def test_managed_pipeline_roles_are_filtered() -> None:
    """Apple exposes 'managed pipeline' evergreen roles — not real postings.
    They must not surface in canonical rows."""
    def handler(request: httpx.Request) -> httpx.Response:
        results = [
            {"positionId": "1", "postingTitle": "Real role",
             "managedPipelineRole": False, "locations": [], "team": {}, "homeOffice": False,
             "standardWeeklyHours": "40", "postingDate": 0, "postDateInGMT": None,
             "reqId": "1-R", "jobSummary": ""},
            {"positionId": "2", "postingTitle": "Pipeline role",
             "managedPipelineRole": True, "locations": [], "team": {}, "homeOffice": False,
             "standardWeeklyHours": "40", "postingDate": 0, "postDateInGMT": None,
             "reqId": "2-R", "jobSummary": ""},
        ]
        payload = {"loaderData": {"search": {"searchResults": results, "totalRecords": 2}}}
        escaped = json.dumps(json.dumps(payload))
        return httpx.Response(
            200,
            text=f'<script>window.__staticRouterHydrationData = JSON.parse({escaped})</script>',
        )

    http = HTTPClient(
        base_url="https://jobs.apple.com",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    try:
        raws = await _adapter(http).discover()
    finally:
        await http.close()

    assert len(raws) == 1
    assert raws[0].title == "Real role"


async def test_normalize_sets_country_and_remote_from_home_office() -> None:
    """A homeOffice=True result must flag every location row as remote,
    regardless of the location text."""
    results = [
        {
            "positionId": "99",
            "postingTitle": "Remote SWE",
            "locations": [
                {"name": "Cupertino", "countryName": "United States of America"},
                {"name": "Austin", "countryName": "United States of America"},
            ],
            "team": {"teamName": "Core OS", "teamCode": "COS"},
            "homeOffice": True,
            "managedPipelineRole": False,
            "standardWeeklyHours": "40",
            "postingDate": 1700000000000,
            "postDateInGMT": "Thu, 23 Nov 2023 00:00:00 GMT",
            "reqId": "99-REQ",
            "jobSummary": "<p>Work from home.</p>",
        }
    ]
    page = {"loaderData": {"search": {"searchResults": results, "totalRecords": 1}}}

    def handler(request: httpx.Request) -> httpx.Response:
        escaped = json.dumps(json.dumps(page))
        return httpx.Response(
            200,
            text=f'<script>window.__staticRouterHydrationData = JSON.parse({escaped})</script>',
        )

    http = HTTPClient(
        base_url="https://jobs.apple.com",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    try:
        adapter = _adapter(http)
        raws = await adapter.discover()
    finally:
        await http.close()

    canonical = adapter.normalize(raws[0])
    assert canonical.workplace_type == "Remote"
    assert len(canonical.locations) == 2
    for loc in canonical.locations:
        assert loc.country == "United States of America"
        assert loc.remote_allowed is True


async def test_filters_pass_through_as_query_params() -> None:
    captured_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        return httpx.Response(200, text=_page_html())

    http = HTTPClient(
        base_url="https://jobs.apple.com",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    adapter = _adapter(
        http,
        {"filters": {"location": "united-states-USA", "team": "apps-and-frameworks-SFTWR-AF"}},
    )
    try:
        await adapter.discover()
    finally:
        await http.close()

    assert captured_urls, "expected at least one request"
    url = captured_urls[0]
    assert "location=united-states-USA" in url
    assert "team=apps-and-frameworks-SFTWR-AF" in url
    assert "page=1" in url


async def test_missing_hydration_raises_clear_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>plain page</body></html>")

    http = HTTPClient(
        base_url="https://jobs.apple.com",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    try:
        with pytest.raises(ValueError, match="hydration"):
            await _adapter(http).discover()
    finally:
        await http.close()


async def test_source_url_includes_slugified_title() -> None:
    """Apple's canonical URL pattern is
    ``/en-us/details/{positionId}/{slug}``; the slug is a kebab-case title."""
    results = [
        {
            "positionId": "200611820",
            "postingTitle": "Senior Software Engineer, Core OS",
            "locations": [{"name": "Cupertino", "countryName": "United States of America"}],
            "team": {}, "homeOffice": False, "managedPipelineRole": False,
            "standardWeeklyHours": "40", "postingDate": 0, "postDateInGMT": None,
            "reqId": "200611820-REQ", "jobSummary": "",
        }
    ]
    page = {"loaderData": {"search": {"searchResults": results, "totalRecords": 1}}}

    def handler(request: httpx.Request) -> httpx.Response:
        escaped = json.dumps(json.dumps(page))
        return httpx.Response(
            200,
            text=f'<script>window.__staticRouterHydrationData = JSON.parse({escaped})</script>',
        )

    http = HTTPClient(
        base_url="https://jobs.apple.com",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    try:
        raws = await _adapter(http).discover()
    finally:
        await http.close()

    assert raws[0].source_url == (
        "https://jobs.apple.com/en-us/details/200611820/senior-software-engineer-core-os"
    )


async def test_empty_first_page_is_retried_then_recovers() -> None:
    pages = [_empty_page_html(), _page_html()]
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        idx = calls["n"]
        calls["n"] += 1
        return httpx.Response(200, text=pages[idx] if idx < len(pages) else _empty_page_html())

    http = HTTPClient(
        base_url="https://jobs.apple.com",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    try:
        raws = await _adapter(http).discover()
    finally:
        await http.close()
    assert raws, "retry of page 1 should have produced jobs"


async def test_persistently_empty_first_page_fails_the_sync() -> None:
    """Never report found=0 for Apple — that would hide a bad response."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, text=_empty_page_html())

    http = HTTPClient(
        base_url="https://jobs.apple.com",
        transport=httpx.MockTransport(handler),
        rate_limit_per_second=0,
    )
    try:
        with pytest.raises(RuntimeError, match="no results on page 1"):
            await _adapter(http).discover()
    finally:
        await http.close()
    assert calls["n"] == 1 + AppleAdapter._EMPTY_FIRST_PAGE_RETRIES
