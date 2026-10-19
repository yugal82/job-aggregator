"""Generic Workday career-portal adapter.

Every Workday-hosted job board shares the same JSON-API shape — only the
hostname + tenant + site slug change. One adapter unlocks dozens of
Fortune 500 companies (Nvidia, Adobe, Intel, Qualcomm, Salesforce, Intuit,
ServiceNow, …).

**List phase** (search):
    POST https://{host}/wday/cxs/{tenant}/{site}/jobs
    body: { "appliedFacets": {...}, "limit": 20, "offset": 0, "searchText": "" }
    → { "total": N, "jobPostings": [ { title, externalPath, locationsText,
                                        postedOn, bulletFields: [reqId] } ] }

**Detail phase** (per record):
    GET https://{host}/wday/cxs/{tenant}/{site}{externalPath}
    → { "jobPostingInfo": { title, location, additionalLocations[],
                            jobDescription (HTML), jobReqId, timeType,
                            startDate, externalUrl, country, ... } }

Each company's config supplies ``host``, ``tenant``, ``site``. Optional
``applied_facets`` dict is passed verbatim as the Workday ``appliedFacets``
payload — useful for pre-filtering (e.g. ``locationCountry`` facets) to
keep daily-sync runtime bounded. A per-request ``User-Agent`` is set
because Workday 403s the default ``python-httpx`` UA.
"""
import logging
from datetime import datetime
from typing import Any

import httpx

from app.adapters.base import JobSourceAdapter
from app.adapters.models import CanonicalJob, CanonicalLocation, RawJob
from app.adapters.registry import register
from app.adapters.utils import (
    content_hash,
    parse_iso_datetime,
    sanitize_requisition_id,
    strip_html,
)

log = logging.getLogger(__name__)

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def _normalize_time_type(value: str | None) -> str | None:
    if not value:
        return None
    mapping = {
        "full time": "Full-time",
        "full-time": "Full-time",
        "part time": "Part-time",
        "part-time": "Part-time",
        "intern": "Internship",
        "contract": "Contract",
        "temporary": "Temporary",
    }
    return mapping.get(value.strip().lower(), value)


def _parse_workday_date(value: str | None) -> datetime | None:
    """`startDate` ships as "YYYY-MM-DD". Fall back to ISO parsing for anything
    richer."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except (ValueError, TypeError):
        return parse_iso_datetime(value)


def _parse_locations(info: dict[str, Any]) -> list[CanonicalLocation]:
    """Primary ``location`` plus any ``additionalLocations``. Workday ships
    the primary country in ``info.country.descriptor`` ("United States of
    America", "India", ...). ``additionalLocations`` are strings only, so
    they inherit the primary country — reasonable since most Workday roles
    stay within a single country (cross-country postings are rare and get a
    separate requisition).

    City/state are left None because Workday's ``location`` is free-form
    (e.g. "Lehi", "San Jose", "US-CA-San Francisco") and our query-time
    regex (``app/filters/country.py``) handles the pattern matching."""
    out: list[CanonicalLocation] = []
    primary = info.get("location")
    additional = info.get("additionalLocations") or []
    country_blob = info.get("country") or {}
    country = country_blob.get("descriptor") if isinstance(country_blob, dict) else None
    for text in [primary, *additional]:
        if not text:
            continue
        lower = text.lower()
        out.append(
            CanonicalLocation(
                location_text=text,
                country=country,
                remote_allowed="remote" in lower or "virtual" in lower,
                hybrid_allowed="hybrid" in lower,
            )
        )
    return out


@register
class WorkdayAdapter(JobSourceAdapter):
    provider = "workday"

    _PAGE_SIZE = 20  # Workday caps most tenants at 20; higher sometimes 400s
    _MAX_PAGES = 500

    def _coords(self) -> tuple[str, str, str]:
        host = self.config.get("host")
        tenant = self.config.get("tenant")
        site = self.config.get("site")
        if not (host and tenant and site):
            raise ValueError(
                f"WorkdayAdapter for '{self.company_slug}' needs host/tenant/site "
                f"in configuration (got {sorted(self.config)})"
            )
        return host, tenant, site

    def _list_url(self) -> str:
        host, tenant, site = self._coords()
        return f"https://{host}/wday/cxs/{tenant}/{site}/jobs"

    def _detail_url(self, external_path: str) -> str:
        host, tenant, site = self._coords()
        return f"https://{host}/wday/cxs/{tenant}/{site}{external_path}"

    def _applied_facets(self) -> dict[str, Any]:
        return self.config.get("applied_facets") or {}

    async def _fetch_detail(self, external_path: str) -> dict[str, Any] | None:
        """A pulled job returns 4xx — skip it, don't fail the sync."""
        response = await self.http.get(
            self._detail_url(external_path), headers=_BROWSER_HEADERS
        )
        if 400 <= response.status_code < 500:
            log.warning(
                "workday detail returned 4xx — skipping",
                extra={
                    "company": self.company_slug,
                    "external_path": external_path,
                    "status": response.status_code,
                },
            )
            return None
        response.raise_for_status()
        return response.json()

    async def discover(self) -> list[RawJob]:
        offset = 0
        all_postings: list[dict[str, Any]] = []
        total: int | None = None

        for _ in range(self._MAX_PAGES):
            response = await self.http.post(
                self._list_url(),
                json={
                    "appliedFacets": self._applied_facets(),
                    "limit": self._PAGE_SIZE,
                    "offset": offset,
                    "searchText": "",
                },
                headers=_BROWSER_HEADERS,
            )
            # Workday redirects to community.workday.com/maintenance-page
            # during scheduled maintenance. Treat as a transient skip rather
            # than crashing the whole sync.
            if 300 <= response.status_code < 400:
                location = response.headers.get("location", "")
                log.warning(
                    "workday redirected (likely maintenance) — skipping sync",
                    extra={
                        "company": self.company_slug,
                        "status": response.status_code,
                        "location": location,
                    },
                )
                raise httpx.HTTPStatusError(
                    f"workday redirected to {location}",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            data = response.json()
            postings = data.get("jobPostings") or []
            if not postings:
                break
            all_postings.extend(postings)
            offset += len(postings)
            if total is None:
                total = data.get("total")
            if total is not None and offset >= total:
                break
        else:
            log.warning(
                "workday pagination hit MAX_PAGES — more jobs may exist",
                extra={
                    "company": self.company_slug,
                    "max_pages": self._MAX_PAGES,
                    "fetched": len(all_postings),
                },
            )

        raws: list[RawJob] = []
        for p in all_postings:
            external_path = p.get("externalPath")
            if not external_path:
                continue
            info = await self._fetch_detail(external_path)
            raws.append(_build_raw(p, info))
        return raws

    async def get_job(self, source_job_id: str) -> RawJob:
        # source_job_id is the Workday ``jobReqId``; we don't have the
        # externalPath without a search. Fall back to a filtered list sweep.
        for raw in await self.discover():
            if raw.source_job_id == source_job_id:
                return raw
        raise LookupError(source_job_id)

    def normalize(self, raw: RawJob) -> CanonicalJob:
        payload = raw.payload
        info = payload.get("jobPostingInfo") or {}
        description = strip_html(info.get("jobDescription"))
        locations = _parse_locations(info)

        return CanonicalJob(
            company_slug=self.company_slug,
            source_provider=self.provider,
            source_job_id=raw.source_job_id,
            title=raw.title,
            description=description,
            locations=locations,
            employment_type=_normalize_time_type(info.get("timeType")),
            workplace_type=None,  # Workday doesn't surface a single flag; see locations
            department=None,
            team=None,
            salary_min=None,
            salary_max=None,
            salary_currency=None,
            posted_at=_parse_workday_date(info.get("startDate")),
            updated_at=None,
            application_url=raw.application_url,
            source_url=raw.source_url,
            requisition_id=sanitize_requisition_id(info.get("jobReqId")),
            raw_data=payload,
            content_hash=content_hash(raw.title, description, raw.location_text),
        )


def _primary_req_id(list_record: dict[str, Any]) -> str | None:
    """Workday puts the req id in ``bulletFields: [reqId]``."""
    fields = list_record.get("bulletFields") or []
    return str(fields[0]) if fields else None


def _build_raw(list_record: dict[str, Any], detail: dict[str, Any] | None) -> RawJob:
    """Fold the list record + optional detail payload into a RawJob.
    Falls back to the list record when the detail call 404'd — we lose the
    description but keep title/url/req so dedup still works."""
    info = dict((detail or {}).get("jobPostingInfo") or {})
    external_path = list_record.get("externalPath") or info.get("externalPath")
    req_id = _primary_req_id(list_record) or info.get("jobReqId")
    title = info.get("title") or list_record.get("title") or ""
    external_url = info.get("externalUrl")

    # When the detail call was unreachable we still want `normalize()` to find
    # SOMETHING in `info.location` so the canonical row has at least one
    # location row — otherwise dedup L3/L4 lose signal.
    if not info.get("location") and list_record.get("locationsText"):
        info["location"] = list_record["locationsText"]

    primary_location = info.get("location")

    payload = {
        "list_record": list_record,
        "jobPostingInfo": info,
    }

    return RawJob(
        source_job_id=str(req_id or external_path),
        source_url=external_url,
        application_url=external_url,
        title=title,
        location_text=primary_location,
        posted_at=_parse_workday_date(info.get("startDate")),
        updated_at=None,
        payload=payload,
    )
