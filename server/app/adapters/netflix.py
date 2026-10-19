"""Netflix Jobs adapter (public explore.jobs.netflix.net feed).

Endpoint:
    GET https://explore.jobs.netflix.net/api/apply/v2/jobs?domain=netflix.com

Pagination via `start` + `num` (we use 100). Returns a top-level
``positions`` list and a numeric ``count`` for the total. Timestamps
``t_create`` / ``t_update`` are **Unix seconds** (not millis).
"""
import logging
from typing import Any

from app.adapters.base import JobSourceAdapter
from app.adapters.models import CanonicalJob, CanonicalLocation, RawJob
from app.adapters.registry import register
from app.adapters.utils import (
    content_hash,
    parse_epoch_seconds,
    sanitize_requisition_id,
    strip_html,
)

log = logging.getLogger(__name__)


def _normalize_workplace(value: str | None) -> str | None:
    if not value:
        return None
    token = str(value).strip().lower().replace("_", "-")
    if token in {"on-site", "onsite"}:
        return "On-site"
    if token == "hybrid":
        return "Hybrid"
    if token == "remote":
        return "Remote"
    return value


def _parse_locations(payload: dict[str, Any]) -> list[CanonicalLocation]:
    """Netflix flattens location into a single string per entry. The
    `locations` list carries one or more strings; fall back to the scalar
    `location` field."""
    texts = payload.get("locations") or ([payload.get("location")] if payload.get("location") else [])
    workplace = (payload.get("work_location_option") or "").lower()
    is_remote = workplace == "remote"
    is_hybrid = workplace == "hybrid"

    out: list[CanonicalLocation] = []
    for text in texts:
        if not text:
            continue
        lower = text.lower()
        out.append(
            CanonicalLocation(
                location_text=text,
                remote_allowed=is_remote or "remote" in lower,
                hybrid_allowed=is_hybrid or "hybrid" in lower,
            )
        )
    return out


def _raw_from_entry(entry: dict[str, Any]) -> RawJob:
    url = entry.get("canonicalPositionUrl")
    return RawJob(
        source_job_id=str(entry["id"]),
        source_url=url,
        application_url=url,
        title=entry.get("name") or "",
        location_text=entry.get("location"),
        posted_at=parse_epoch_seconds(entry.get("t_create")),
        updated_at=parse_epoch_seconds(entry.get("t_update")),
        payload=entry,
    )


@register
class NetflixAdapter(JobSourceAdapter):
    provider = "netflix-careers"

    # Netflix's endpoint caps page size at ~10 regardless of what we ask for,
    # so bail based on `count` (the total) or an empty page rather than the
    # usual len(page) < page_size short-circuit.
    _MAX_PAGES = 200
    _PAGE_SIZE = 100

    def _domain(self) -> str:
        return self.config.get("domain") or "netflix.com"

    async def discover(self) -> list[RawJob]:
        start = 0
        all_positions: list[dict[str, Any]] = []
        total: int | None = None

        for _ in range(self._MAX_PAGES):
            response = await self.http.get(
                "/api/apply/v2/jobs",
                params={
                    "domain": self._domain(),
                    "start": start,
                    "num": self._PAGE_SIZE,
                },
            )
            response.raise_for_status()
            data = response.json()
            positions = data.get("positions") or []
            if not positions:
                break
            all_positions.extend(positions)
            start += len(positions)
            if total is None:
                total = data.get("count")
            if total is not None and start >= total:
                break
        else:
            log.warning(
                "netflix pagination hit MAX_PAGES — more jobs may exist",
                extra={"max_pages": self._MAX_PAGES, "fetched": len(all_positions)},
            )
        return [_raw_from_entry(p) for p in all_positions]

    async def get_job(self, source_job_id: str) -> RawJob:
        for raw in await self.discover():
            if raw.source_job_id == source_job_id:
                return raw
        raise LookupError(source_job_id)

    def normalize(self, raw: RawJob) -> CanonicalJob:
        payload = raw.payload
        description = strip_html(payload.get("job_description"))
        locations = _parse_locations(payload)
        workplace_type = _normalize_workplace(payload.get("work_location_option"))

        return CanonicalJob(
            company_slug=self.company_slug,
            source_provider=self.provider,
            source_job_id=raw.source_job_id,
            title=raw.title,
            description=description,
            locations=locations,
            employment_type=None,  # Netflix doesn't surface this on the feed
            workplace_type=workplace_type,
            department=payload.get("department"),
            team=payload.get("business_unit"),
            salary_min=None,
            salary_max=None,
            salary_currency=None,
            posted_at=raw.posted_at,
            updated_at=raw.updated_at,
            application_url=raw.application_url,
            source_url=raw.source_url,
            requisition_id=sanitize_requisition_id(
                payload.get("ats_job_id") or payload.get("display_job_id")
            ),
            raw_data=payload,
            content_hash=content_hash(raw.title, description, raw.location_text),
        )
