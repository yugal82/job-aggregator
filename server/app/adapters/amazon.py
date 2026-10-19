"""Amazon Jobs adapter.

Public API:
    GET https://www.amazon.jobs/en/search.json

Pagination via `offset` + `result_limit` (max 100 per page). Returns:
    { "error": null, "hits": <int>, "jobs": [ ... ] }

Jobs expose `id_icims` as the stable numeric id used in URLs. Dates:
    `posted_date` — human-readable like "October  3, 2026" (note double space).
    `updated_time` — relative like "1 day" (not useful; ignored).

Default `config.filters` restricts to US software-dev roles — tune via the YAML
if you want a wider cut. Hard cap at `max_pages * result_limit` to avoid
runaway crawls on very large result sets.
"""
import json
import logging
from datetime import datetime
from typing import Any

from app.adapters.base import JobSourceAdapter
from app.adapters.models import CanonicalJob, CanonicalLocation, RawJob
from app.adapters.registry import register
from app.adapters.utils import (
    content_hash,
    sanitize_requisition_id,
    strip_html,
)

log = logging.getLogger(__name__)

_DEFAULT_FILTERS: dict[str, Any] = {
    "category[]": "software-development",
    "normalized_country_code[]": "USA",
    "sort": "recent",
}


def _parse_posted_date(value: str | None) -> datetime | None:
    """Amazon ships `posted_date` as "October  3, 2026" (sometimes with a
    double-space between month and day). Try common variants."""
    if not value:
        return None
    text = " ".join(value.split())  # collapse multiple spaces
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=None)
        except ValueError:
            continue
    return None


def _parse_locations(payload: dict[str, Any]) -> list[CanonicalLocation]:
    """Amazon's `locations` field is a list of JSON-string blobs — each entry
    needs its own ``json.loads``. Fall back to the flat ``location`` string if
    the list is missing or unparseable."""
    out: list[CanonicalLocation] = []
    raw_list = payload.get("locations") or []

    for entry in raw_list:
        try:
            parsed = json.loads(entry) if isinstance(entry, str) else entry
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(parsed, dict):
            continue
        location_text = (
            parsed.get("locationNonStemming")
            or parsed.get("normalizedLocation")
            or parsed.get("location")
        )
        type_ = (parsed.get("type") or "").upper()
        out.append(
            CanonicalLocation(
                location_text=location_text,
                city=parsed.get("normalizedCityName") or parsed.get("city"),
                state=parsed.get("region") or parsed.get("normalizedStateName"),
                country=parsed.get("countryIso2a"),
                remote_allowed=type_ == "VIRTUAL" or "remote" in (location_text or "").lower(),
                hybrid_allowed=type_ == "HYBRID",
            )
        )

    if out:
        return out

    # Fallback: flat `location` string + the top-level city/state/country_code.
    location_text = payload.get("location")
    if not location_text:
        return []
    return [
        CanonicalLocation(
            location_text=location_text,
            city=payload.get("city"),
            state=payload.get("state"),
            country=payload.get("country_code"),
            remote_allowed="remote" in location_text.lower(),
        )
    ]


def _normalize_employment_type(value: str | None) -> str | None:
    if not value:
        return None
    mapping = {
        "full-time": "Full-time",
        "part-time": "Part-time",
        "intern": "Internship",
        "temporary": "Temporary",
    }
    return mapping.get(value.lower(), value)


def _raw_from_entry(entry: dict[str, Any]) -> RawJob:
    icims = entry.get("id_icims") or entry.get("id")
    source_url = (
        f"https://www.amazon.jobs{entry['job_path']}"
        if entry.get("job_path")
        else entry.get("url_next_step")
    )
    return RawJob(
        source_job_id=str(icims),
        source_url=source_url,
        application_url=entry.get("url_next_step") or source_url,
        title=entry.get("title") or "",
        location_text=entry.get("location"),
        posted_at=_parse_posted_date(entry.get("posted_date")),
        updated_at=None,  # `updated_time` is a relative string, not a timestamp
        payload=entry,
    )


@register
class AmazonAdapter(JobSourceAdapter):
    provider = "amazon-careers"

    _MAX_PAGES = 50     # upper bound on crawl depth
    _PAGE_SIZE = 100

    def _filters(self) -> dict[str, Any]:
        return self.config.get("filters") or _DEFAULT_FILTERS

    async def discover(self) -> list[RawJob]:
        offset = 0
        all_jobs: list[dict[str, Any]] = []
        for _ in range(self._MAX_PAGES):
            params = {
                **self._filters(),
                "offset": offset,
                "result_limit": self._PAGE_SIZE,
            }
            response = await self.http.get("/en/search.json", params=params)
            response.raise_for_status()
            data = response.json()
            jobs = data.get("jobs") or []
            all_jobs.extend(jobs)
            if len(jobs) < self._PAGE_SIZE:
                break
            offset += self._PAGE_SIZE
        else:
            log.warning(
                "amazon pagination hit MAX_PAGES — more jobs may exist",
                extra={"max_pages": self._MAX_PAGES, "fetched": len(all_jobs)},
            )
        return [_raw_from_entry(j) for j in all_jobs]

    async def get_job(self, source_job_id: str) -> RawJob:
        # Amazon's search endpoint doesn't support exact-id lookup; fall back
        # to a filtered discover and pick out the match.
        for raw in await self.discover():
            if raw.source_job_id == source_job_id:
                return raw
        raise LookupError(source_job_id)

    def normalize(self, raw: RawJob) -> CanonicalJob:
        payload = raw.payload
        text_parts = [
            payload.get("description"),
            payload.get("basic_qualifications"),
            payload.get("preferred_qualifications"),
        ]
        description = strip_html("\n\n".join(p for p in text_parts if p))

        locations = _parse_locations(payload)

        return CanonicalJob(
            company_slug=self.company_slug,
            source_provider=self.provider,
            source_job_id=raw.source_job_id,
            title=raw.title,
            description=description,
            locations=locations,
            employment_type=_normalize_employment_type(payload.get("job_schedule_type")),
            workplace_type=None,  # Amazon doesn't expose a single flag; see location.type
            department=payload.get("job_family") or payload.get("job_category"),
            team=(payload.get("team") or {}).get("label")
            if isinstance(payload.get("team"), dict)
            else None,
            salary_min=None,
            salary_max=None,
            salary_currency=None,
            posted_at=raw.posted_at,
            updated_at=None,
            application_url=raw.application_url,
            source_url=raw.source_url,
            requisition_id=sanitize_requisition_id(payload.get("id_icims")),
            raw_data=payload,
            content_hash=content_hash(raw.title, description, raw.location_text),
        )
