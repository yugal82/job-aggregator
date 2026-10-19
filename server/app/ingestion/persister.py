"""Persist canonical jobs into the relational schema.

`create_job` — brand-new job (never seen).
`update_job` — job matched by dedupe; refresh fields, bump last_seen_at,
              ensure a JobSource row for the current source exists.

Both call ``select_canonical_url`` after mutating ``job_sources`` so the
stored ``canonical_url`` always reflects the best-priority source we have.
A JobVersion row is written on create and on every content change.
"""
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.models import CanonicalJob, CanonicalLocation
from app.ingestion.canonical_url import select_canonical_url
from app.ingestion.fingerprint import compute_fingerprint
from app.models.enums import JobStatus
from app.models.job import Job
from app.models.job_location import JobLocation
from app.models.job_source import JobSource
from app.models.job_version import JobVersion


def _primary_location(canonical: CanonicalJob) -> CanonicalLocation | None:
    return canonical.locations[0] if canonical.locations else None


def _version_row(job: Job, version: int) -> JobVersion:
    return JobVersion(
        job_id=job.id,
        version=version,
        content_hash=job.content_hash or "",
        title=job.canonical_title,
        description=job.description,
        employment_type=job.employment_type,
        workplace_type=job.workplace_type,
        department=job.department,
        team=job.team,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
    )


async def _next_version(session: AsyncSession, job_id) -> int:
    last = await session.scalar(
        select(func.max(JobVersion.version)).where(JobVersion.job_id == job_id)
    )
    return (last or 0) + 1


async def create_job(
    session: AsyncSession,
    canonical: CanonicalJob,
    *,
    company_id: int,
    source_id: int,
) -> Job:
    now = datetime.now(timezone.utc)

    job = Job(
        company_id=company_id,
        canonical_title=canonical.title,
        description=canonical.description,
        employment_type=canonical.employment_type,
        workplace_type=canonical.workplace_type,
        posted_at=canonical.posted_at,
        first_seen_at=now,
        last_seen_at=now,
        salary_min=canonical.salary_min,
        salary_max=canonical.salary_max,
        salary_currency=canonical.salary_currency,
        department=canonical.department,
        team=canonical.team,
        level=canonical.level,
        application_url=canonical.application_url,
        content_hash=canonical.content_hash,
        fingerprint=compute_fingerprint(canonical),
        requisition_id=canonical.requisition_id,
        status=JobStatus.ACTIVE,
        consecutive_missed_syncs=0,
    )
    session.add(job)
    await session.flush()

    for loc in canonical.locations:
        session.add(_location_row(job.id, loc))

    primary = _primary_location(canonical)
    session.add(
        JobSource(
            job_id=job.id,
            source_id=source_id,
            source_job_id=canonical.source_job_id,
            source_url=canonical.source_url,
            source_application_url=canonical.application_url,
            source_title=canonical.title,
            source_location=primary.location_text if primary else None,
            source_posted_at=canonical.posted_at,
            raw_payload=canonical.raw_data,
            is_active=True,
        )
    )
    await session.flush()

    job.canonical_url = await select_canonical_url(session, job.id)
    session.add(_version_row(job, version=1))

    await session.flush()
    return job


async def update_job(
    session: AsyncSession,
    job: Job,
    canonical: CanonicalJob,
    *,
    source_id: int,
) -> bool:
    """Update the matched job. Returns True iff canonical content changed."""
    now = datetime.now(timezone.utc)

    job.last_seen_at = now
    job.consecutive_missed_syncs = 0
    if job.status == JobStatus.CLOSED:
        job.status = JobStatus.ACTIVE
        job.closed_at = None

    content_changed = job.content_hash != canonical.content_hash

    # `level` isn't part of content_hash — a scraper can start populating
    # it on a later sync without triggering an UPDATED status. Mirror it
    # through unconditionally so backfills land without needing a content
    # change. Only mutate when it actually differs.
    if canonical.level is not None and job.level != canonical.level:
        job.level = canonical.level

    if content_changed:
        job.canonical_title = canonical.title
        job.description = canonical.description
        job.employment_type = canonical.employment_type
        job.workplace_type = canonical.workplace_type
        job.department = canonical.department
        job.team = canonical.team
        job.salary_min = canonical.salary_min
        job.salary_max = canonical.salary_max
        job.salary_currency = canonical.salary_currency
        job.application_url = canonical.application_url
        job.content_hash = canonical.content_hash
        job.fingerprint = compute_fingerprint(canonical)
        job.status = JobStatus.UPDATED

        # Replace locations wholesale — simpler than diffing for MVP.
        await session.execute(delete(JobLocation).where(JobLocation.job_id == job.id))
        for loc in canonical.locations:
            session.add(_location_row(job.id, loc))

    # Attach or refresh the JobSource row for this (source, source_job_id).
    existing_js = (
        await session.execute(
            select(JobSource).where(
                JobSource.source_id == source_id,
                JobSource.source_job_id == canonical.source_job_id,
            )
        )
    ).scalar_one_or_none()

    primary = _primary_location(canonical)
    if existing_js is None:
        session.add(
            JobSource(
                job_id=job.id,
                source_id=source_id,
                source_job_id=canonical.source_job_id,
                source_url=canonical.source_url,
                source_application_url=canonical.application_url,
                source_title=canonical.title,
                source_location=primary.location_text if primary else None,
                source_posted_at=canonical.posted_at,
                raw_payload=canonical.raw_data,
                is_active=True,
            )
        )
    else:
        existing_js.last_seen_at = now
        existing_js.is_active = True
        existing_js.source_url = canonical.source_url
        existing_js.source_application_url = canonical.application_url
        existing_js.source_title = canonical.title
        existing_js.source_location = primary.location_text if primary else None
        existing_js.source_posted_at = canonical.posted_at
        existing_js.raw_payload = canonical.raw_data

    await session.flush()

    # Re-evaluate canonical_url now that job_sources is up to date — a new
    # higher-priority source might have just arrived.
    job.canonical_url = await select_canonical_url(session, job.id)

    if content_changed:
        version = await _next_version(session, job.id)
        session.add(_version_row(job, version=version))

    await session.flush()
    return content_changed


def _location_row(job_id, loc: CanonicalLocation) -> JobLocation:
    return JobLocation(
        job_id=job_id,
        city=loc.city,
        state=loc.state,
        country=loc.country,
        postal_code=loc.postal_code,
        remote_allowed=loc.remote_allowed,
        hybrid_allowed=loc.hybrid_allowed,
        location_text=loc.location_text,
    )
