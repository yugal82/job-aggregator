"""Test-only adapter that returns a scripted list of RawJobs.

Not registered globally. Instantiated directly by pipeline tests.
"""
import hashlib
from typing import Any

from app.adapters.base import JobSourceAdapter
from app.adapters.models import CanonicalJob, CanonicalLocation, RawJob


def _hash(*parts: str | None) -> str:
    return hashlib.sha256("|".join(p or "" for p in parts).encode()).hexdigest()


def make_raw(
    *,
    source_job_id: str,
    title: str = "Engineer",
    location_text: str | None = "Remote",
    requisition_id: str | None = None,
    application_url: str | None = None,
) -> RawJob:
    return RawJob(
        source_job_id=source_job_id,
        title=title,
        location_text=location_text,
        source_url=application_url,
        application_url=application_url,
        payload={
            "id": source_job_id,
            "title": title,
            "location_text": location_text,
            "requisition_id": requisition_id,
            "application_url": application_url,
        },
    )


class StubAdapter(JobSourceAdapter):
    provider = "stub"

    def __init__(
        self,
        *,
        company_slug: str,
        raw_jobs: list[RawJob],
    ) -> None:
        super().__init__(http=None, config={}, company_slug=company_slug)  # type: ignore[arg-type]
        self._raw_jobs = raw_jobs

    async def discover(self) -> list[RawJob]:
        return list(self._raw_jobs)

    async def get_job(self, source_job_id: str) -> RawJob:  # pragma: no cover
        for rj in self._raw_jobs:
            if rj.source_job_id == source_job_id:
                return rj
        raise LookupError(source_job_id)

    def normalize(self, raw: RawJob) -> CanonicalJob:
        payload: dict[str, Any] = raw.payload
        loc = (
            [CanonicalLocation(
                location_text=raw.location_text,
                remote_allowed="remote" in (raw.location_text or "").lower(),
            )]
            if raw.location_text
            else []
        )
        return CanonicalJob(
            company_slug=self.company_slug,
            source_provider=self.provider,
            source_job_id=raw.source_job_id,
            title=raw.title,
            description=payload.get("description"),
            locations=loc,
            application_url=raw.application_url,
            source_url=raw.source_url,
            requisition_id=payload.get("requisition_id"),
            raw_data=payload,
            content_hash=_hash(raw.title, raw.location_text, payload.get("description")),
        )
