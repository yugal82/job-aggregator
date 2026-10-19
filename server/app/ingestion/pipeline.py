"""End-to-end sync orchestration.

Three transactions per run:
  1. Insert a SyncRun row with status=RUNNING so we always have a record even
     if the work below crashes.
  2. Fetch + persist raw payload + dedupe/persist canonical jobs + lifecycle.
  3. Finalize SyncRun (SUCCESS/FAILED) and update company_source timestamps.

Failures in phase 2 are recorded to SyncRun in phase 3, then re-raised so the
caller sees the exception.
"""
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.adapters.base import JobSourceAdapter
from app.ingestion.dedupe import find_matching_job
from app.ingestion.lifecycle import mark_stale_jobs_missed
from app.ingestion.persister import create_job, update_job
from app.ingestion.raw_store import save_raw_document
from app.models.company_source import CompanySource
from app.models.enums import SyncRunStatus
from app.models.sync_run import SyncRun

log = logging.getLogger(__name__)


@dataclass
class SyncOutcome:
    sync_run_id: int
    status: SyncRunStatus
    jobs_found: int
    jobs_new: int
    jobs_updated: int
    jobs_closed: int
    error: str | None


async def _create_sync_run(
    session_factory: async_sessionmaker,
    *,
    company_source_id: int,
    adapter_name: str,
    started_at: datetime,
) -> int:
    async with session_factory() as session:
        run = SyncRun(
            company_source_id=company_source_id,
            adapter=adapter_name,
            status=SyncRunStatus.RUNNING,
            started_at=started_at,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run.id


async def _finalize_sync_run(
    session_factory: async_sessionmaker,
    *,
    sync_run_id: int,
    company_source_id: int,
    jobs_found: int,
    jobs_new: int,
    jobs_updated: int,
    jobs_closed: int,
    error: str | None,
) -> SyncRunStatus:
    completed_at = datetime.now(timezone.utc)
    status = SyncRunStatus.FAILED if error else SyncRunStatus.SUCCESS
    async with session_factory() as session:
        run = await session.get(SyncRun, sync_run_id)
        if run is not None:
            run.completed_at = completed_at
            run.status = status
            run.jobs_found = jobs_found
            run.jobs_new = jobs_new
            run.jobs_updated = jobs_updated
            run.jobs_closed = jobs_closed
            run.error = error

        cs = await session.get(CompanySource, company_source_id)
        if cs is not None:
            cs.last_attempted_sync = completed_at
            if status == SyncRunStatus.SUCCESS:
                cs.last_successful_sync = completed_at

        await session.commit()
    return status


async def run_sync(
    *,
    session_factory: async_sessionmaker,
    adapter: JobSourceAdapter,
    company_id: int,
    source_id: int,
    company_source_id: int,
    adapter_name: str,
) -> SyncOutcome:
    started_at = datetime.now(timezone.utc)
    sync_run_id = await _create_sync_run(
        session_factory,
        company_source_id=company_source_id,
        adapter_name=adapter_name,
        started_at=started_at,
    )

    jobs_found = 0
    jobs_new = 0
    jobs_updated = 0
    jobs_closed = 0
    error: str | None = None

    try:
        raw_jobs = await adapter.discover()
        jobs_found = len(raw_jobs)

        async with session_factory() as session:
            await save_raw_document(
                session,
                source_id=source_id,
                company_id=company_id,
                content=json.dumps([rj.payload for rj in raw_jobs], default=str),
                content_type="application/json",
                http_status=200,
            )

            seen: set[str] = set()
            for raw in raw_jobs:
                canonical = adapter.normalize(raw)
                seen.add(canonical.source_job_id)

                existing = await find_matching_job(
                    session, canonical, company_id=company_id, source_id=source_id
                )
                if existing is None:
                    await create_job(
                        session, canonical, company_id=company_id, source_id=source_id
                    )
                    jobs_new += 1
                else:
                    changed = await update_job(
                        session, existing, canonical, source_id=source_id
                    )
                    if changed:
                        jobs_updated += 1

            jobs_closed = await mark_stale_jobs_missed(
                session,
                company_id=company_id,
                source_id=source_id,
                seen_source_job_ids=seen,
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"[:1000]
        log.exception("sync failed", extra={"sync_run_id": sync_run_id})
        status = await _finalize_sync_run(
            session_factory,
            sync_run_id=sync_run_id,
            company_source_id=company_source_id,
            jobs_found=jobs_found,
            jobs_new=jobs_new,
            jobs_updated=jobs_updated,
            jobs_closed=jobs_closed,
            error=error,
        )
        raise
    else:
        status = await _finalize_sync_run(
            session_factory,
            sync_run_id=sync_run_id,
            company_source_id=company_source_id,
            jobs_found=jobs_found,
            jobs_new=jobs_new,
            jobs_updated=jobs_updated,
            jobs_closed=jobs_closed,
            error=None,
        )

    log.info(
        "sync completed",
        extra={
            "sync_run_id": sync_run_id,
            "status": status.value,
            "found": jobs_found,
            "new": jobs_new,
            "updated": jobs_updated,
            "closed": jobs_closed,
        },
    )
    return SyncOutcome(
        sync_run_id=sync_run_id,
        status=status,
        jobs_found=jobs_found,
        jobs_new=jobs_new,
        jobs_updated=jobs_updated,
        jobs_closed=jobs_closed,
        error=error,
    )
