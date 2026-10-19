"""Microsoft Careers adapter — GitHub-mirrored scraper feed.

Microsoft's public ``apply.careers.microsoft.com/api/pcsx/search`` API is
unstable (frequent 403s + schema drift) and requires a per-job detail
round-trip for descriptions. We've swapped it for a user-owned scraper
that keeps a canonical ``jobs.json`` on GitHub and runs on a cron:

    https://github.com/yugal82/msft-jobs
    https://raw.githubusercontent.com/yugal82/msft-jobs/main/jobs.json

The adapter is a one-call fetch + parse. The source file is
**append-only** — the scraper never prunes closed roles — so we DO NOT
rely on the pipeline's "missing-from-source" close detection here (every
synced job keeps appearing until the scraper owner trims the file).

Response shape:
    { "last_updated": "...", "total_jobs": N, "jobs": [ ... ] }

Per-job fields consumed:
    displayJobId          "200060544"         → source_job_id, requisition_id
    name                  "Software Engineer" → canonical title
    standardizedLocations ["Redmond, WA, US"] → location rows
    locations             ["United States, Washington, Redmond"]
                                              → fallback when standardized is empty
    postedTs              unix seconds        → posted_at
    workLocationOption    "onsite"|"remote"|"hybrid" → workplace_type / remote flag
    atsJobId              "200060544"         → requisition_id fallback
    positionUrl           "/careers/job/<id>" → source URL (prefixed with host)
    department            "Software Engineering"
    level                 "IC2" | "IC3/IC4" | "Intern" | None
                                              → canonical.level (filterable
                                                via /api/jobs?level=IC2).
                                                Older payloads used ``ic_level``.
"""
import logging
import re
from typing import Any

from app.adapters.base import JobSourceAdapter
from app.adapters.models import CanonicalJob, CanonicalLocation, RawJob
from app.adapters.registry import register
from app.adapters.utils import (
    content_hash,
    parse_epoch_seconds,
    sanitize_requisition_id,
)

log = logging.getLogger(__name__)

_IC_LEVEL_RE = re.compile(r"^IC\s*-?\s*(\d+)$", re.IGNORECASE)
_LEVEL_MAX_LEN = 32  # jobs.level is VARCHAR(32)


def _normalize_level(value: str | None) -> str | None:
    """Canonicalize the scraper's level. Each ``/``-separated part is
    trimmed and IC variants (``IC 2`` / ``ic-2``) become ``IC2``, so
    ``"IC3 / ic 4"`` → ``"IC3/IC4"``. Non-IC bands (``Intern``, ``ATR-B``)
    pass through trimmed — the level filter matches any part."""
    if not value:
        return None
    parts = []
    for part in str(value).split("/"):
        part = part.strip()
        if not part:
            continue
        m = _IC_LEVEL_RE.match(part)
        parts.append(f"IC{m.group(1)}" if m else part)
    level = "/".join(parts)
    if not level or len(level) > _LEVEL_MAX_LEN:
        return None
    return level

# Prefixed onto `positionUrl` so the stored URL is browseable. We keep the
# well-known Microsoft careers host rather than guessing the scraper's
# upstream origin — that way links go to the real posting if MSFT keeps
# the URL stable even when the scraper's path format evolves.
_CAREERS_HOST = "https://jobs.careers.microsoft.com"

_WORKPLACE_MAP = {
    "onsite": "Onsite",
    "on-site": "Onsite",
    "remote": "Remote",
    "hybrid": "Hybrid",
}


def _normalize_workplace(value: str | None) -> str | None:
    if not value:
        return None
    return _WORKPLACE_MAP.get(value.strip().lower(), value)


def _parse_locations(entry: dict[str, Any]) -> list[CanonicalLocation]:
    """Prefer ``standardizedLocations`` ("Redmond, WA, US") — those are
    the clean 3-component strings we can split. Fall back to ``locations``
    which is more verbose but less structured. If both are empty, bail."""
    standardized = entry.get("standardizedLocations") or []
    raw_locations = entry.get("locations") or []

    source = standardized if standardized else raw_locations
    if not source:
        return []

    remote_flag = (entry.get("workLocationOption") or "").strip().lower() == "remote"
    hybrid_flag = (entry.get("workLocationOption") or "").strip().lower() == "hybrid"

    out: list[CanonicalLocation] = []
    seen: set[str] = set()
    for text in source:
        if not isinstance(text, str) or not text.strip():
            continue
        key = text.strip().lower()
        if key in seen:
            continue
        seen.add(key)

        # Standardized form: "City, State, Country" — split on commas; the
        # last chunk is country, middle is state, first is city. Verbose
        # form ("United States, Washington, Redmond") puts country first,
        # so we only trust the split when the format is standardized.
        city = state = country = None
        if standardized and source is standardized:
            parts = [p.strip() for p in text.split(",") if p.strip()]
            if len(parts) >= 3:
                city, state, country = parts[0], parts[1], parts[2]
            elif len(parts) == 2:
                city, country = parts[0], parts[1]
            elif len(parts) == 1:
                city = parts[0]

        lowered = text.lower()
        out.append(
            CanonicalLocation(
                location_text=text,
                city=city,
                state=state,
                country=country,
                remote_allowed=remote_flag or "remote" in lowered,
                hybrid_allowed=hybrid_flag or "hybrid" in lowered,
            )
        )
    return out


def _source_url(position_url: str | None) -> str | None:
    """``positionUrl`` is a relative path (``/careers/job/<id>``). Prefix
    with the public MSFT careers host so the stored link resolves."""
    if not position_url:
        return None
    if position_url.startswith("http://") or position_url.startswith("https://"):
        return position_url
    if not position_url.startswith("/"):
        position_url = "/" + position_url
    return f"{_CAREERS_HOST}{position_url}"


def _raw_from_entry(entry: dict[str, Any]) -> RawJob:
    source_job_id = str(entry.get("displayJobId") or entry.get("id") or "")
    locations_list = entry.get("standardizedLocations") or entry.get("locations") or []
    primary_location = locations_list[0] if locations_list else None
    source_url = _source_url(entry.get("positionUrl"))

    return RawJob(
        source_job_id=source_job_id,
        source_url=source_url,
        application_url=source_url,
        title=entry.get("name") or "",
        location_text=primary_location,
        posted_at=parse_epoch_seconds(entry.get("postedTs")),
        updated_at=None,
        payload=entry,
    )


@register
class MicrosoftAdapter(JobSourceAdapter):
    """Microsoft careers via GitHub-hosted scraper mirror."""

    provider = "microsoft-careers"

    _DEFAULT_URL = (
        "https://raw.githubusercontent.com/yugal82/msft-jobs/main/jobs.json"
    )

    def _url(self) -> str:
        return self.config.get("url") or self._DEFAULT_URL

    async def discover(self) -> list[RawJob]:
        response = await self.http.get(self._url())
        response.raise_for_status()
        data = response.json()

        jobs = data.get("jobs") if isinstance(data, dict) else None
        if not isinstance(jobs, list):
            raise ValueError(
                "microsoft jobs feed did not contain a `jobs` list "
                f"(top keys: {list(data.keys()) if isinstance(data, dict) else type(data).__name__})"
            )
        return [_raw_from_entry(e) for e in jobs if isinstance(e, dict)]

    async def get_job(self, source_job_id: str) -> RawJob:
        for raw in await self.discover():
            if raw.source_job_id == source_job_id:
                return raw
        raise LookupError(source_job_id)

    def normalize(self, raw: RawJob) -> CanonicalJob:
        payload = raw.payload
        return CanonicalJob(
            company_slug=self.company_slug,
            source_provider=self.provider,
            source_job_id=raw.source_job_id,
            title=raw.title,
            description=None,  # scraper doesn't capture descriptions
            locations=_parse_locations(payload),
            employment_type=None,  # not in scraper payload
            workplace_type=_normalize_workplace(payload.get("workLocationOption")),
            department=payload.get("department"),
            team=None,
            level=_normalize_level(payload.get("level") or payload.get("ic_level")),
            salary_min=None,
            salary_max=None,
            salary_currency=None,
            posted_at=raw.posted_at,
            updated_at=None,
            application_url=raw.application_url,
            source_url=raw.source_url,
            requisition_id=sanitize_requisition_id(
                payload.get("atsJobId") or payload.get("displayJobId")
            ),
            raw_data=payload,
            content_hash=content_hash(raw.title, None, raw.location_text),
        )
