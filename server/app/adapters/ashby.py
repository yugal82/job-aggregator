"""Ashby ATS adapter.

Public API (unusually, a POST):
    POST https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true

Returns { "apiVersion": "1", "jobs": [...] }.
"""
from decimal import Decimal
from typing import Any

from app.adapters.base import JobSourceAdapter
from app.adapters.models import CanonicalJob, CanonicalLocation, RawJob
from app.adapters.registry import register
from app.adapters.utils import (
    content_hash,
    parse_iso_datetime,
    sanitize_requisition_id,
    strip_html,
)


_EMPLOYMENT_TYPE_MAP = {
    "FullTime": "Full-time",
    "PartTime": "Part-time",
    "Intern": "Internship",
    "Contract": "Contract",
    "Temporary": "Temporary",
}


def _normalize_employment_type(value: str | None) -> str | None:
    if not value:
        return None
    return _EMPLOYMENT_TYPE_MAP.get(str(value), str(value))


def _parse_locations(entry: dict[str, Any]) -> list[CanonicalLocation]:
    primary = entry.get("location")
    secondaries = entry.get("secondaryLocations") or []

    texts: list[str] = []
    if primary:
        texts.append(primary)
    for loc in secondaries:
        # `secondaryLocations` items are dicts { "location": "..." }
        if isinstance(loc, dict) and loc.get("location"):
            texts.append(loc["location"])
        elif isinstance(loc, str):
            texts.append(loc)

    if not texts:
        return []

    is_remote = bool(entry.get("isRemote"))
    out: list[CanonicalLocation] = []
    for text in texts:
        lowered = text.lower()
        out.append(
            CanonicalLocation(
                location_text=text,
                remote_allowed=is_remote or "remote" in lowered,
                hybrid_allowed="hybrid" in lowered,
            )
        )
    return out


def _parse_compensation(entry: dict[str, Any]) -> tuple[Decimal | None, Decimal | None, str | None]:
    """Extract a (min, max, currency) triple from Ashby's compensation block.

    Ashby returns compensation as a list of tiers; use the first salary-shaped
    tier we can find. Silent failure is fine — Phase 4 doesn't require salary.
    """
    comp = entry.get("compensation") or {}
    # `compensationTierSummary` is a display string; `compensationTiers` is the
    # structured breakdown we actually want.
    tiers = comp.get("compensationTiers") or []
    if not isinstance(tiers, list):
        return None, None, None
    for tier in tiers:
        if not isinstance(tier, dict):
            continue
        components = tier.get("components") or []
        for c in components:
            if not isinstance(c, dict):
                continue
            comp_type = (c.get("compensationType") or "").lower()
            if "salary" not in comp_type:
                continue
            value = c.get("compensationValue") or {}
            currency = value.get("currencyCode")
            min_v = value.get("minValue")
            max_v = value.get("maxValue")
            try:
                return (
                    Decimal(str(min_v)) if min_v is not None else None,
                    Decimal(str(max_v)) if max_v is not None else None,
                    currency,
                )
            except (ValueError, ArithmeticError):
                return None, None, None
    return None, None, None


def _raw_from_entry(entry: dict[str, Any]) -> RawJob:
    return RawJob(
        source_job_id=str(entry["id"]),
        source_url=entry.get("jobUrl"),
        application_url=entry.get("applyUrl") or entry.get("jobUrl"),
        title=entry.get("title") or "",
        location_text=entry.get("location"),
        posted_at=parse_iso_datetime(entry.get("publishedAt")),
        updated_at=parse_iso_datetime(entry.get("updatedAt")),
        payload=entry,
    )


@register
class AshbyAdapter(JobSourceAdapter):
    provider = "ashby"

    def _org(self) -> str:
        org = self.config.get("job_board_name") or self.config.get("org")
        if not org:
            raise ValueError(
                f"AshbyAdapter for '{self.company_slug}' missing "
                "config.job_board_name (or config.org)"
            )
        return org

    async def discover(self) -> list[RawJob]:
        org = self._org()
        response = await self.http.post(
            f"/posting-api/job-board/{org}",
            params={"includeCompensation": "true"},
            json={},
        )
        response.raise_for_status()
        data = response.json()
        return [
            _raw_from_entry(entry)
            for entry in data.get("jobs", [])
            if entry.get("isListed", True)
        ]

    async def get_job(self, source_job_id: str) -> RawJob:
        # Ashby's public API doesn't expose per-job GET; refetch and filter.
        for raw in await self.discover():
            if raw.source_job_id == source_job_id:
                return raw
        raise LookupError(source_job_id)

    def normalize(self, raw: RawJob) -> CanonicalJob:
        payload = raw.payload
        description = (
            payload.get("descriptionPlain")
            or strip_html(payload.get("descriptionHtml"))
        )
        locations = _parse_locations(payload)
        salary_min, salary_max, currency = _parse_compensation(payload)

        return CanonicalJob(
            company_slug=self.company_slug,
            source_provider=self.provider,
            source_job_id=raw.source_job_id,
            title=raw.title,
            description=description,
            locations=locations,
            employment_type=_normalize_employment_type(payload.get("employmentType")),
            workplace_type=(
                "Remote" if payload.get("isRemote") else None
            ),
            department=payload.get("department"),
            team=payload.get("team"),
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=currency,
            posted_at=raw.posted_at,
            updated_at=raw.updated_at,
            application_url=raw.application_url,
            source_url=raw.source_url,
            requisition_id=sanitize_requisition_id(payload.get("customFields", {}).get("requisitionId") if isinstance(payload.get("customFields"), dict) else None),
            raw_data=payload,
            content_hash=content_hash(raw.title, description, raw.location_text),
        )
