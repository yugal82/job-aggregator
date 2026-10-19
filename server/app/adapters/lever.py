"""Lever ATS adapter.

Public API:
    GET https://api.lever.co/v0/postings/{site}?mode=json

Returns a JSON array of postings. `createdAt`/`updatedAt` are milliseconds
since epoch (JS convention).
"""
from typing import Any

from app.adapters.base import JobSourceAdapter
from app.adapters.models import CanonicalJob, CanonicalLocation, RawJob
from app.adapters.registry import register
from app.adapters.utils import (
    content_hash,
    parse_epoch_millis,
    sanitize_requisition_id,
    strip_html,
)


def _normalize_workplace(value: str | None) -> str | None:
    """Lever uses "on-site" / "hybrid" / "remote"; normalize casing."""
    if not value:
        return None
    text = str(value).strip().lower().replace("_", "-")
    if text in {"on-site", "onsite"}:
        return "On-site"
    if text == "hybrid":
        return "Hybrid"
    if text == "remote":
        return "Remote"
    return value


def _location_flags(text: str | None) -> tuple[bool, bool]:
    if not text:
        return False, False
    lowered = text.lower()
    return "remote" in lowered, "hybrid" in lowered


def _parse_locations(categories: dict[str, Any], workplace_type: str | None) -> list[CanonicalLocation]:
    all_locations = categories.get("allLocations") or []
    primary = categories.get("location")

    # Fall back to primary if allLocations isn't populated
    texts = list(all_locations) if all_locations else ([primary] if primary else [])
    if not texts:
        return []

    workplace_lower = (workplace_type or "").lower()
    workplace_remote = workplace_lower == "remote"
    workplace_hybrid = workplace_lower == "hybrid"

    out: list[CanonicalLocation] = []
    for text in texts:
        if not text:
            continue
        remote, hybrid = _location_flags(text)
        out.append(
            CanonicalLocation(
                location_text=text,
                remote_allowed=remote or workplace_remote,
                hybrid_allowed=hybrid or workplace_hybrid,
            )
        )
    return out


def _raw_from_entry(entry: dict[str, Any]) -> RawJob:
    categories = entry.get("categories") or {}
    return RawJob(
        source_job_id=str(entry["id"]),
        source_url=entry.get("hostedUrl"),
        application_url=entry.get("applyUrl") or entry.get("hostedUrl"),
        title=entry.get("text") or "",
        location_text=categories.get("location"),
        posted_at=parse_epoch_millis(entry.get("createdAt")),
        updated_at=parse_epoch_millis(entry.get("updatedAt")),
        payload=entry,
    )


@register
class LeverAdapter(JobSourceAdapter):
    provider = "lever"

    def _site(self) -> str:
        site = self.config.get("site")
        if not site:
            raise ValueError(
                f"LeverAdapter for '{self.company_slug}' missing config.site"
            )
        return site

    async def discover(self) -> list[RawJob]:
        site = self._site()
        response = await self.http.get(f"/v0/postings/{site}", params={"mode": "json"})
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            return []
        return [_raw_from_entry(entry) for entry in data]

    async def get_job(self, source_job_id: str) -> RawJob:
        site = self._site()
        response = await self.http.get(
            f"/v0/postings/{site}/{source_job_id}", params={"mode": "json"}
        )
        response.raise_for_status()
        return _raw_from_entry(response.json())

    def normalize(self, raw: RawJob) -> CanonicalJob:
        payload = raw.payload
        categories = payload.get("categories") or {}

        description = (
            payload.get("descriptionPlain")
            or strip_html(payload.get("description"))
        )
        additional = payload.get("additionalPlain") or strip_html(payload.get("additional"))
        if additional:
            description = f"{description}\n\n{additional}" if description else additional

        workplace_type = _normalize_workplace(payload.get("workplaceType"))
        locations = _parse_locations(categories, payload.get("workplaceType"))

        return CanonicalJob(
            company_slug=self.company_slug,
            source_provider=self.provider,
            source_job_id=raw.source_job_id,
            title=raw.title,
            description=description,
            locations=locations,
            employment_type=categories.get("commitment"),
            workplace_type=workplace_type,
            department=categories.get("department"),
            team=categories.get("team"),
            salary_min=None,
            salary_max=None,
            salary_currency=None,
            posted_at=raw.posted_at,
            updated_at=raw.updated_at,
            application_url=raw.application_url,
            source_url=raw.source_url,
            requisition_id=sanitize_requisition_id(payload.get("requisitionCode")),
            raw_data=payload,
            content_hash=content_hash(raw.title, description, raw.location_text),
        )
