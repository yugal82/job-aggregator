"""Apple Jobs adapter.

Apple's careers portal (``jobs.apple.com``) is a React Router SSR app.
Every public search page embeds the full search payload as a hydration
blob inside a ``<script>`` tag:

    window.__staticRouterHydrationData = JSON.parse("<escaped JSON>")

Decode that blob → navigate to ``loaderData.search`` →
``{ searchResults: [...], totalRecords: N, queryParams: {...} }``.

Each ``searchResults[i]`` already carries every field we need for the
canonical row — no per-job detail round-trip required. Fields of interest:

    postingTitle, jobSummary          — title + preview-length description
    positionId, reqId                 — stable ids ("200648762", "200648762-123")
    locations[]                       — list of dicts with countryName, name
                                        (city/metro/region are often empty)
    team.teamName / team.teamCode     — org bucket
    postingDate (ms epoch) /
    postDateInGMT (RFC-1123)          — two timestamp formats
    standardWeeklyHours               — "40", "20" → full-/part-time
    homeOffice (bool)                 — remote flag
    managedPipelineRole (bool)        — "pipeline" roles aren't real postings

Pagination: hit ``/en-us/search?page=N`` for successive pages. 20 results
per page is Apple's default.
"""
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from app.adapters.base import JobSourceAdapter
from app.adapters.models import CanonicalJob, CanonicalLocation, RawJob
from app.adapters.registry import register
from app.adapters.utils import content_hash, strip_html

log = logging.getLogger(__name__)

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_HYDRATION_RE = re.compile(
    r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\("((?:\\.|[^"\\])*)"\)',
    re.DOTALL,
)

_PAGE_SIZE = 20   # Apple's fixed page size on this endpoint
_MAX_PAGES = 500  # hard upper bound on crawl depth


def _extract_hydration(html: str) -> dict[str, Any]:
    """Decode ``window.__staticRouterHydrationData`` from an Apple
    search/detail page. The embedded blob is a JSON-encoded JSON string:
    first ``json.loads`` turns ``"..."`` into a regular string with the
    escapes resolved, the second parses that string into the real tree."""
    m = _HYDRATION_RE.search(html)
    if not m:
        raise ValueError("apple page is missing hydration data")
    inner = json.loads('"' + m.group(1) + '"')
    return json.loads(inner)


def _employment_type_from_hours(hours: str | None) -> str | None:
    """Apple's ``standardWeeklyHours`` is a string like "40" or "20".
    Everything < 35 is part-time; everything else is full-time."""
    if not hours:
        return None
    try:
        value = float(hours)
    except (ValueError, TypeError):
        return None
    return "Full-time" if value >= 35 else "Part-time"


def _parse_posting_date(result: dict[str, Any]) -> datetime | None:
    """Prefer ``postDateInGMT`` (RFC-1123) over ``postingDate`` (ms epoch);
    both appear on every record but the RFC-1123 form keeps timezone info."""
    gmt = result.get("postDateInGMT")
    if isinstance(gmt, str):
        try:
            return datetime.strptime(gmt, "%a, %d %b %Y %H:%M:%S %Z").replace(
                tzinfo=timezone.utc
            )
        except (ValueError, TypeError):
            pass
    epoch_ms = result.get("postingDate")
    if isinstance(epoch_ms, (int, float)):
        return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    return None


def _parse_locations(result: dict[str, Any]) -> list[CanonicalLocation]:
    """Apple ships multiple location rows per posting under ``locations[]``.
    Each entry has ``countryName``, ``name`` (city or country name), and
    sparse ``city``/``metro``/``region`` fields that are usually empty."""
    rows = result.get("locations") or []
    home_office = bool(result.get("homeOffice"))
    out: list[CanonicalLocation] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = (row.get("name") or "").strip()
        country = (row.get("countryName") or "").strip() or None
        city = (row.get("city") or "").strip() or None
        state = (row.get("stateProvince") or "").strip() or None
        # name is often the city ("Austin") OR the country ("United States");
        # dedupe by (name, country).
        key = (name.lower(), (country or "").lower())
        if key in seen:
            continue
        seen.add(key)
        location_text = name or country or ""
        if not location_text:
            continue
        lowered = location_text.lower()
        out.append(
            CanonicalLocation(
                location_text=location_text,
                city=city or (name if country and name != country else None),
                state=state,
                country=country,
                remote_allowed=home_office or "remote" in lowered,
                hybrid_allowed=False,
            )
        )
    return out


def _detail_url(position_id: str, posting_title: str) -> str:
    """Mirror Apple's canonical URL pattern:
        https://jobs.apple.com/en-us/details/{positionId}/{slug}

    The slug is a lower-kebab transform of ``postingTitle``; we approximate
    with a safe fallback so the URL is at least browseable."""
    slug = re.sub(r"[^a-z0-9]+", "-", (posting_title or "").lower()).strip("-")
    slug = slug or "role"
    return f"https://jobs.apple.com/en-us/details/{position_id}/{slug}"


def _raw_from_result(result: dict[str, Any]) -> RawJob:
    position_id = str(result.get("positionId") or result.get("jobPositionId") or "")
    posting_title = result.get("postingTitle") or result.get("transformedPostingTitle") or ""
    source_url = _detail_url(position_id, posting_title)
    locations = result.get("locations") or []
    primary_loc_text = None
    if locations and isinstance(locations[0], dict):
        primary_loc_text = locations[0].get("name") or locations[0].get("countryName")
    return RawJob(
        source_job_id=position_id,
        source_url=source_url,
        application_url=source_url,
        title=posting_title,
        location_text=primary_loc_text,
        posted_at=_parse_posting_date(result),
        updated_at=None,
        payload=result,
    )


@register
class AppleAdapter(JobSourceAdapter):
    """Apple careers adapter. Reads inline search-hydration data; no
    detail fetches, since the summary payload is enough for the canonical
    row and Apple rate-limits aggressively."""

    provider = "apple-careers"

    _MAX_PAGES = _MAX_PAGES
    _PAGE_SIZE = _PAGE_SIZE

    def _filters(self) -> dict[str, Any]:
        return self.config.get("filters") or {}

    def _search_url(self, page: int) -> str:
        """Compose ``/en-us/search`` with pagination + yaml-configured filters.
        Filters pass through verbatim as query parameters — see Apple's
        public search UI for the current filter keys (location, team, ...)."""
        params = {**self._filters(), "page": page}
        return "/en-us/search?" + httpx.QueryParams(params).__str__()

    async def _fetch_page(self, page: int) -> dict[str, Any]:
        response = await self.http.get(self._search_url(page), headers=_BROWSER_HEADERS)
        response.raise_for_status()
        hydration = _extract_hydration(response.text)
        search = hydration.get("loaderData", {}).get("search", {}) or {}
        return search

    async def discover(self) -> list[RawJob]:
        all_results: list[dict[str, Any]] = []
        total: int | None = None
        page = 1

        for _ in range(self._MAX_PAGES):
            search = await self._fetch_page(page)
            results = search.get("searchResults") or []
            if not results:
                break
            all_results.extend(results)
            if total is None:
                total = search.get("totalRecords")
            if total is not None and len(all_results) >= total:
                break
            if len(results) < self._PAGE_SIZE:
                break
            page += 1
        else:
            log.warning(
                "apple pagination hit MAX_PAGES — more jobs may exist",
                extra={
                    "company": self.company_slug,
                    "max_pages": self._MAX_PAGES,
                    "fetched": len(all_results),
                },
            )

        # Apple's "managed pipeline" roles aren't real postings — they're
        # evergreen requisitions used by recruiters as a funnel. Drop them.
        filtered = [r for r in all_results if not r.get("managedPipelineRole")]
        return [_raw_from_result(r) for r in filtered]

    async def get_job(self, source_job_id: str) -> RawJob:
        # No stable id-only endpoint; a filtered discover is the fallback.
        for raw in await self.discover():
            if raw.source_job_id == source_job_id:
                return raw
        raise LookupError(source_job_id)

    def normalize(self, raw: RawJob) -> CanonicalJob:
        payload = raw.payload
        description = strip_html(payload.get("jobSummary"))
        team = payload.get("team") or {}
        team_name = team.get("teamName") if isinstance(team, dict) else None
        team_code = team.get("teamCode") if isinstance(team, dict) else None

        return CanonicalJob(
            company_slug=self.company_slug,
            source_provider=self.provider,
            source_job_id=raw.source_job_id,
            title=raw.title,
            description=description,
            locations=_parse_locations(payload),
            employment_type=_employment_type_from_hours(
                payload.get("standardWeeklyHours")
            ),
            workplace_type="Remote" if payload.get("homeOffice") else None,
            department=team_name,
            team=team_code,
            salary_min=None,
            salary_max=None,
            salary_currency=None,
            posted_at=raw.posted_at,
            updated_at=None,
            application_url=raw.application_url,
            source_url=raw.source_url,
            requisition_id=payload.get("reqId") or raw.source_job_id or None,
            raw_data=payload,
            content_hash=content_hash(raw.title, description, raw.location_text),
        )
