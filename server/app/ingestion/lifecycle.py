"""End-of-sync lifecycle: for jobs not seen this run, increment their miss
counter, then close them once the grace period lapses.

Threshold is 3 misses per the roadmap ("2-3 consecutive misses"). This means a
job needs to be absent from three consecutive syncs before it flips to CLOSED.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobStatus
from app.models.job import Job
from app.models.job_source import JobSource

CLOSE_AFTER_MISSES = 3


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
