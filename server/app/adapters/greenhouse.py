"""Greenhouse ATS adapter.

Public API:
    GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
    GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}
"""
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

# Kept as private re-exports so existing tests importing them keep working.
_sanitize_requisition_id = sanitize_requisition_id
_strip_html = strip_html
_parse_iso_datetime = parse_iso_datetime
_content_hash = content_hash


def _parse_metadata(entries: list[dict[str, Any]] | None) -> dict[str, str | None]:
    result: dict[str, str | None] = {"employment_type": None, "workplace_type": None}
    for entry in entries or []:
        name = (entry.get("name") or "").lower()
        value = entry.get("value")
        if value is None:
            continue
        text = str(value).strip() or None
        if "employment" in name:
            result["employment_type"] = text
        elif "workplace" in name or "remote" in name:
            result["workplace_type"] = text
    return result


def _parse_locations(location_text: str | None) -> list[CanonicalLocation]:
    if not location_text:
        return []
    lowered = location_text.lower()
    return [
        CanonicalLocation(
            location_text=location_text,
            remote_allowed="remote" in lowered,
            hybrid_allowed="hybrid" in lowered,
        )
    ]


def _raw_from_entry(entry: dict[str, Any]) -> RawJob:
    location = entry.get("location") or {}
    return RawJob(
        source_job_id=str(entry["id"]),
        source_url=entry.get("absolute_url"),
        application_url=entry.get("absolute_url"),
        title=entry.get("title") or "",
        location_text=location.get("name") if isinstance(location, dict) else None,
        posted_at=parse_iso_datetime(entry.get("first_published") or entry.get("updated_at")),
        updated_at=parse_iso_datetime(entry.get("updated_at")),
        payload=entry,
    )


@register
class GreenhouseAdapter(JobSourceAdapter):
    provider = "greenhouse"

    def _board_token(self) -> str:
        token = self.config.get("board_token")
        if not token:
            raise ValueError(
                f"GreenhouseAdapter for '{self.company_slug}' missing config.board_token"
            )
        return token

    async def discover(self) -> list[RawJob]:
        board = self._board_token()
        response = await self.http.get(f"/v1/boards/{board}/jobs", params={"content": "true"})
        response.raise_for_status()
        data = response.json()
        return [_raw_from_entry(entry) for entry in data.get("jobs", [])]

    async def get_job(self, source_job_id: str) -> RawJob:
        board = self._board_token()
        response = await self.http.get(f"/v1/boards/{board}/jobs/{source_job_id}")
        response.raise_for_status()
        return _raw_from_entry(response.json())

    def normalize(self, raw: RawJob) -> CanonicalJob:
        payload = raw.payload
        description = strip_html(payload.get("content"))

        departments = payload.get("departments") or []
        department = departments[0]["name"] if departments else None
        team = departments[-1]["name"] if len(departments) > 1 else None

        meta = _parse_metadata(payload.get("metadata"))
        locations = _parse_locations(raw.location_text)

        return CanonicalJob(
            company_slug=self.company_slug,
            source_provider=self.provider,
            source_job_id=raw.source_job_id,
            title=raw.title,
            description=description,
            locations=locations,
            employment_type=meta["employment_type"],
            workplace_type=meta["workplace_type"],
            department=department,
            team=team,
            salary_min=None,
            salary_max=None,
            salary_currency=None,
            posted_at=raw.posted_at,
            updated_at=raw.updated_at,
            application_url=raw.application_url,
            source_url=raw.source_url,
            requisition_id=sanitize_requisition_id(payload.get("requisition_id")),
            raw_data=payload,
            content_hash=content_hash(raw.title, description, raw.location_text),
        )
