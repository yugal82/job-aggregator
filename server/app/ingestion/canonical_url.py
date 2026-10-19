"""Pick the "canonical" URL for a job across its multiple sources.

Priority order (design doc §29):
    official > ats > board

Called after any mutation that could add/change the set of active job_sources
for a job, so the stored ``canonical_url`` always points at the best-source
URL we know about.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.url_utils import normalize_url
from app.models.enums import SourceType
from app.models.job_source import JobSource
from app.models.source import Source

_SOURCE_TYPE_PRIORITY = {
    SourceType.OFFICIAL: 0,
    SourceType.ATS: 1,
    SourceType.BOARD: 2,
}


async def select_canonical_url(session: AsyncSession, job_id: uuid.UUID) -> str | None:
    """Return the best (lowest-priority-number) URL across the job's active sources."""
    rows = (
        await session.execute(
            select(JobSource, Source.type)
            .join(Source, JobSource.source_id == Source.id)
            .where(JobSource.job_id == job_id, JobSource.is_active.is_(True))
        )
    ).all()

    if not rows:
        return None

    best = min(
        rows,
        key=lambda row: _SOURCE_TYPE_PRIORITY.get(row[1], 99),
    )
    best_js: JobSource = best[0]
    return normalize_url(best_js.source_application_url or best_js.source_url)
