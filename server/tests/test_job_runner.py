import uuid

from prometheus_client import REGISTRY
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.base import JobSourceAdapter
from app.adapters.registry import _REGISTRY
from app.models.company_source import CompanySource
from app.models.enums import SourceType
from app.models.sync_run import SyncRun
from app.observability.metrics import (
    JOBS_FETCHED_TOTAL,
    SYNC_DURATION_SECONDS,
    SYNC_SKIPPED_TOTAL,
)
from app.repositories.company import CompanyRepo
from app.repositories.source import SourceRepo
from app.services.sync_lock import SyncLock
from app.workers.job_runner import lock_key_for, run_scheduled_sync


class RunnerNoopAdapter(JobSourceAdapter):
    provider = "runner-noop"

    async def discover(self):
        return []

    async def get_job(self, source_job_id):  # pragma: no cover
        raise LookupError(source_job_id)

    def normalize(self, raw):  # pragma: no cover
        raise NotImplementedError


async def _seed(db_session: AsyncSession) -> tuple[int, int, int, str, str]:
    slug = f"runner-{uuid.uuid4().hex[:8]}"
    company = await CompanyRepo(db_session).create(name="Runner", slug=slug)
    source = await SourceRepo(db_session).create(
        name=f"RunnerSource-{slug}",
        type=SourceType.ATS,
        provider="runner-noop",
    )
    cs = CompanySource(
        company_id=company.id,
        source_id=source.id,
        adapter="runner-noop",
        configuration={},
        enabled=True,
    )
    db_session.add(cs)
    await db_session.commit()
    return company.id, source.id, cs.id, slug, "runner-noop"


def _target(company_id, source_id, cs_id, slug, provider) -> dict:
    return {
        "adapter_name": "runner-noop",
        "provider": provider,
        "base_url": "",
        "config": {},
        "company_slug": slug,
        "company_id": company_id,
        "source_id": source_id,
        "company_source_id": cs_id,
    }


def _sample_value(metric, labels: dict) -> float:
    """Read the current Prometheus counter/histogram value for given labels."""
    # prometheus_client exposes internal storage via ._metrics
    child = metric.labels(**labels)
    if hasattr(child, "_sum"):
        return child._sum.get()  # type: ignore[attr-defined]
    if hasattr(child, "_value"):
        return child._value.get()  # type: ignore[attr-defined]
    return 0.0


async def test_run_scheduled_sync_records_sync_run_and_metric(
    db_session: AsyncSession, session_factory: async_sessionmaker
) -> None:
    company_id, source_id, cs_id, slug, provider = await _seed(db_session)
    labels = {"provider": provider, "company": slug}

    _REGISTRY["runner-noop"] = RunnerNoopAdapter
    try:
        before_duration = _sample_value(SYNC_DURATION_SECONDS, labels)
        await run_scheduled_sync(
            _target(company_id, source_id, cs_id, slug, provider),
            session_factory=session_factory,
        )
    finally:
        _REGISTRY.pop("runner-noop", None)

    run = (await db_session.execute(select(SyncRun))).scalars().first()
    assert run is not None
    assert run.status.value == "success"
    assert run.jobs_found == 0

    # Duration histogram bumped
    after_duration = _sample_value(SYNC_DURATION_SECONDS, labels)
    assert after_duration > before_duration


async def test_run_scheduled_sync_skips_when_locked(
    db_session: AsyncSession, session_factory: async_sessionmaker
) -> None:
    company_id, source_id, cs_id, slug, provider = await _seed(db_session)
    labels = {"provider": provider, "company": slug}

    _REGISTRY["runner-noop"] = RunnerNoopAdapter
    holder = SyncLock(lock_key_for(slug, provider))
    assert await holder.acquire() is True
    try:
        before_skip = _sample_value(SYNC_SKIPPED_TOTAL, labels)
        await run_scheduled_sync(
            _target(company_id, source_id, cs_id, slug, provider),
            session_factory=session_factory,
        )
        after_skip = _sample_value(SYNC_SKIPPED_TOTAL, labels)
    finally:
        await holder.release()
        _REGISTRY.pop("runner-noop", None)

    # No SyncRun should have been created for this run — we bailed before starting.
    assert after_skip == before_skip + 1
    runs = (await db_session.execute(select(SyncRun))).scalars().all()
    assert runs == []
