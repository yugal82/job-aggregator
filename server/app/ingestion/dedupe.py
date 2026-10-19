"""Deduplication levels 1-4 from design doc §28.

Level 5 (semantic similarity via embeddings) arrives in a later phase.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.models import CanonicalJob
from app.ingestion.fingerprint import compute_fingerprint
from app.ingestion.url_utils import normalize_url
from app.models.job import Job
from app.models.job_source import JobSource

log = logging.getLogger(__name__)


async def find_matching_job(
    session: AsyncSession,
    canonical: CanonicalJob,
    company_id: int,
    source_id: int,
) -> Job | None:
    """Return the existing Job that this canonical record refers to, or None."""

    # L1 — exact source id match (job_sources unique on (source_id, source_job_id))
    l1 = await session.execute(
        select(Job)
        .join(JobSource, JobSource.job_id == Job.id)
        .where(
            JobSource.source_id == source_id,
            JobSource.source_job_id == canonical.source_job_id,
        )
    )
    match = l1.scalar_one_or_none()
    if match is not None:
        return match

    # L2 — requisition_id within the same company
    if canonical.requisition_id:
        l2 = await session.execute(
            select(Job).where(
                Job.company_id == company_id,
                Job.requisition_id == canonical.requisition_id,
            )
        )
        match = l2.scalar_one_or_none()
        if match is not None:
            return match

    # L3 — normalized canonical URL within the same company
    normalized = normalize_url(canonical.application_url or canonical.source_url)
    if normalized:
        l3 = await session.execute(
            select(Job).where(
                Job.company_id == company_id,
                Job.canonical_url == normalized,
            )
        )
        match = l3.scalar_one_or_none()
        if match is not None:
            return match

    # L4 — normalized content fingerprint within the same company.
    # Order by Job.id so re-syncs pick the same winner deterministically.
    # A pretty-close fingerprint (same title + short preview description +
    # same location) can match multiple existing rows at some adapters —
    # Apple in particular posts near-template preview text across many
    # retail/engineering roles. Pick the lowest-id match in that case and
    # log so we have signal if a sync starts collapsing lots of distinct
    # roles onto one row.
    fingerprint = compute_fingerprint(canonical)
    if fingerprint:
        l4 = await session.execute(
            select(Job)
            .where(
                Job.company_id == company_id,
                Job.fingerprint == fingerprint,
            )
            .order_by(Job.id)
            .limit(2)
        )
        matches = l4.scalars().all()
        if len(matches) > 1:
            log.warning(
                "L4 fingerprint matched multiple jobs; picking lowest-id",
                extra={
                    "company_id": company_id,
                    "fingerprint": fingerprint,
                    "incoming_source_job_id": canonical.source_job_id,
                },
            )
        if matches:
            return matches[0]

    return None
