"""End-of-sync lifecycle: for jobs not seen this run, increment their miss
counter, then close them once the grace period lapses.

Threshold is 3 misses per the roadmap ("2-3 consecutive misses"). This means a
job needs to be absent from three consecutive syncs before it flips to CLOSED.

Partial-discovery guard: when a sync sees under ``MIN_SEEN_RATIO`` of the
source's currently active jobs, the response is treated as truncated (Apple
has served a 19-result page in place of ~2,700) and no misses are recorded.
A real mass removal therefore stalls closing until the drop is fixed or the
ratio is lowered — preferable to wiping a company's listings on a bad page.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobStatus
from app.models.job import Job
from app.models.job_source import JobSource

CLOSE_AFTER_MISSES = 3

# Skip miss-marking when a sync sees less than this share of active jobs...
MIN_SEEN_RATIO = 0.5
# ...but only once the source is big enough for the ratio to mean anything.
MIN_ACTIVE_FOR_GUARD = 20

log = logging.getLogger(__name__)


async def mark_stale_jobs_missed(
    session: AsyncSession,
    *,
    company_id: int,
    source_id: int,
    seen_source_job_ids: set[str],
) -> int:
    """Bump miss counters; close jobs that reach the threshold.

    Returns the number of jobs newly transitioned to CLOSED by this call.
    """
    now = datetime.now(timezone.utc)

    rows = (
        await session.execute(
            select(Job, JobSource)
            .join(JobSource, JobSource.job_id == Job.id)
            .where(
                Job.company_id == company_id,
                JobSource.source_id == source_id,
                JobSource.is_active.is_(True),
            )
        )
    ).all()

    active = len(rows)
    seen_active = sum(1 for _, js in rows if js.source_job_id in seen_source_job_ids)
    if active >= MIN_ACTIVE_FOR_GUARD and seen_active < active * MIN_SEEN_RATIO:
        log.warning(
            "partial discovery — skipping miss marking",
            extra={
                "company_id": company_id,
                "source_id": source_id,
                "active": active,
                "seen_active": seen_active,
            },
        )
        return 0

    newly_closed = 0
    for job, js in rows:
        if js.source_job_id in seen_source_job_ids:
            continue

        job.consecutive_missed_syncs = (job.consecutive_missed_syncs or 0) + 1

        if (
            job.consecutive_missed_syncs >= CLOSE_AFTER_MISSES
            and job.status != JobStatus.CLOSED
        ):
            job.status = JobStatus.CLOSED
            job.closed_at = now
            js.is_active = False
            newly_closed += 1

    await session.flush()
    return newly_closed
