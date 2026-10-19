"""Atlassian careers adapter.

Atlassian hosts its canonical careers data at an iCIMS portal
(``globalcareers-atlassian.icims.com``) but exposes a public JSON
proxy at:

    GET https://www.atlassian.com/endpoint/careers/listings

The response is a flat JSON array (~340 jobs today) with every field
inline — no second detail round-trip required. Each entry has:

    id             int        iCIMS job id
    title          str
    type           str        "Full-Time" | "Part-Time" | "Intern" | ...
    locations      list[str]  free-form strings:
                              "Bengaluru - India -   Bengaluru,  560071 India"
                              "Remote - India - Remote"
                              "Remote - Remote"
    category       str        high-level department
    overview       str (HTML)
    responsibilities str (HTML)
    qualifications   str (HTML)
    applyUrl       str        iCIMS apply link
    portalJobPost: { portalUrl, updatedDate ("YYYY-MM-DD HH:MM AM/PM") }
"""
import logging
import re
from datetime import datetime
from typing import Any

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
    "Accept": "application/json",
}


def _parse_updated_date(value: str | None) -> datetime | None:
    """`updatedDate` ships as "2026-09-24 03:33 PM" (12-hour clock)."""
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d %I:%M %p")
    except (ValueError, TypeError):
        return None


# Atlassian's location strings carry structure in their dash-separated chunks:
#   "San Francisco - United States - Remote"
#   "Bengaluru - India -   Bengaluru,  560071 India"
#   "Remote - Remote"                              → remote
#   "Remote - India - Remote"                      → remote in India
# We split on " - " and probe both ends: country usually sits in position [1]
# (and sometimes [0] when the first chunk is itself "Remote").
_SPLIT = re.compile(r"\s+-\s+")


def _parse_location(text: str) -> CanonicalLocation:
    text = text.strip()
    lowered = text.lower()
    parts = [p.strip() for p in _SPLIT.split(text) if p.strip()]

    # Position 1 is country for "City - Country - ..." entries. For
    # "Remote - Country - ..." we also want position 1 as the country.
    # "Remote - Remote" has no country.
    country: str | None = None
    city: str | None = None
    if len(parts) >= 2:
        candidate = parts[1]
        if candidate.lower() != "remote":
            country = candidate
    if parts and parts[0].lower() not in ("remote", "virtual"):
        city = parts[0]

    return CanonicalLocation(
        location_text=text,
        city=city,
        country=country,
        remote_allowed="remote" in lowered or "virtual" in lowered,
        hybrid_allowed="hybrid" in lowered,
    )


def _parse_locations(entries: list[str] | None) -> list[CanonicalLocation]:
    seen: set[str] = set()
    out: list[CanonicalLocation] = []
    for text in entries or []:
        if not isinstance(text, str) or not text.strip():
            continue
        key = text.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(_parse_location(text))
    return out


_EMPLOYMENT_MAP = {
    "full-time": "Full-time",
    "full time": "Full-time",
    "part-time": "Part-time",
    "part time": "Part-time",
    "intern": "Internship",
    "internship": "Internship",
    "contract": "Contract",
    "temporary": "Temporary",
}


def _normalize_employment(value: str | None) -> str | None:
    if not value:
        return None
    return _EMPLOYMENT_MAP.get(value.strip().lower(), value)


def _raw_from_entry(entry: dict[str, Any]) -> RawJob:
    portal = entry.get("portalJobPost") or {}
    canonical_url = portal.get("portalUrl") if isinstance(portal, dict) else None
    locations = entry.get("locations") or []
    primary_text = locations[0] if locations else None
    return RawJob(
        source_job_id=str(entry.get("id") or ""),
        source_url=canonical_url,
        application_url=entry.get("applyUrl") or canonical_url,
        title=entry.get("title") or "",
        location_text=primary_text,
        posted_at=_parse_updated_date(portal.get("updatedDate")) if isinstance(portal, dict) else None,
        updated_at=_parse_updated_date(portal.get("updatedDate")) if isinstance(portal, dict) else None,
        payload=entry,
    )


@register
class AtlassianAdapter(JobSourceAdapter):
    provider = "atlassian-careers"

    _LISTINGS_PATH = "/endpoint/careers/listings"

    async def discover(self) -> list[RawJob]:
        response = await self.http.get(self._LISTINGS_PATH, headers=_BROWSER_HEADERS)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError(
                f"atlassian listings returned {type(data).__name__}, expected list"
            )
        return [_raw_from_entry(e) for e in data if isinstance(e, dict)]

    async def get_job(self, source_job_id: str) -> RawJob:
        # No per-id endpoint — all jobs ship inline on the listing. Fall back
        # to a filtered discover.
        for raw in await self.discover():
            if raw.source_job_id == source_job_id:
                return raw
        raise LookupError(source_job_id)

    def normalize(self, raw: RawJob) -> CanonicalJob:
        payload = raw.payload
        description = strip_html(
            "\n\n".join(
                part
                for part in (
                    payload.get("overview"),
                    payload.get("responsibilities"),
                    payload.get("qualifications"),
                )
                if part
            )
        )

        return CanonicalJob(
            company_slug=self.company_slug,
            source_provider=self.provider,
            source_job_id=raw.source_job_id,
            title=raw.title,
            description=description,
            locations=_parse_locations(payload.get("locations")),
            employment_type=_normalize_employment(payload.get("type")),
            workplace_type=None,  # inferred per-location via remote_allowed
            department=payload.get("category"),
            team=None,
            salary_min=None,
            salary_max=None,
            salary_currency=None,
            posted_at=raw.posted_at,
            updated_at=raw.updated_at,
            application_url=raw.application_url,
            source_url=raw.source_url,
            requisition_id=raw.source_job_id or None,
            raw_data=payload,
            content_hash=content_hash(raw.title, description, raw.location_text),
        )
