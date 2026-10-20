from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ingestion.lifecycle import CLOSE_AFTER_MISSES, MIN_ACTIVE_FOR_GUARD
from app.ingestion.pipeline import run_sync
from app.models.company import Company
from app.models.company_source import CompanySource
from app.models.enums import JobStatus, SourceType, SyncRunStatus
from app.models.job import Job
from app.models.job_source import JobSource
from app.models.raw_source_document import RawSourceDocument
from app.models.source import Source
from app.models.sync_run import SyncRun
from app.repositories.company import CompanyRepo
from app.repositories.source import SourceRepo
from tests._stub_adapter import StubAdapter, make_raw


async def _setup_company_source(db_session: AsyncSession):
    company = await CompanyRepo(db_session).create(name="Stripe", slug="stripe")
    source = await SourceRepo(db_session).create(
        name="Greenhouse", type=SourceType.ATS, provider="greenhouse"
    )
    cs = CompanySource(
        company_id=company.id,
        source_id=source.id,
        adapter="stub",
        configuration={},
        enabled=True,
    )
    db_session.add(cs)
    await db_session.commit()
    return company, source, cs


async def test_pipeline_creates_new_jobs_on_first_run(
    db_session: AsyncSession, session_factory: async_sessionmaker
) -> None:
    company, source, cs = await _setup_company_source(db_session)
    adapter = StubAdapter(
        company_slug="stripe",
        raw_jobs=[
            make_raw(source_job_id="1", title="Backend"),
            make_raw(source_job_id="2", title="Frontend"),
        ],
    )

    outcome = await run_sync(
        session_factory=session_factory,
        adapter=adapter,
        company_id=company.id,
        source_id=source.id,
        company_source_id=cs.id,
        adapter_name="stub",
    )

    assert outcome.status == SyncRunStatus.SUCCESS
    assert outcome.jobs_found == 2
    assert outcome.jobs_new == 2
    assert outcome.jobs_updated == 0
    assert outcome.jobs_closed == 0

    total_jobs = await db_session.scalar(select(func.count()).select_from(Job))
    assert total_jobs == 2
    total_sources = await db_session.scalar(select(func.count()).select_from(JobSource))
    assert total_sources == 2
    total_raw = await db_session.scalar(select(func.count()).select_from(RawSourceDocument))
    assert total_raw == 1


async def test_pipeline_is_idempotent(
    db_session: AsyncSession, session_factory: async_sessionmaker
) -> None:
    company, source, cs = await _setup_company_source(db_session)
    raw_jobs = [
        make_raw(source_job_id="1", title="Backend"),
        make_raw(source_job_id="2", title="Frontend"),
    ]
    adapter = StubAdapter(company_slug="stripe", raw_jobs=raw_jobs)

    first = await run_sync(
        session_factory=session_factory,
        adapter=adapter,
        company_id=company.id,
        source_id=source.id,
        company_source_id=cs.id,
        adapter_name="stub",
    )
    second = await run_sync(
        session_factory=session_factory,
        adapter=adapter,
        company_id=company.id,
        source_id=source.id,
        company_source_id=cs.id,
        adapter_name="stub",
    )

    assert first.jobs_new == 2
    assert second.jobs_new == 0
    assert second.jobs_updated == 0

    total_jobs = await db_session.scalar(select(func.count()).select_from(Job))
    assert total_jobs == 2  # no duplicates

    # last_seen_at should have been bumped on the second run
    jobs = (await db_session.execute(select(Job))).scalars().all()
    for job in jobs:
        assert job.last_seen_at >= job.first_seen_at


async def test_pipeline_detects_content_change(
    db_session: AsyncSession, session_factory: async_sessionmaker
) -> None:
    company, source, cs = await _setup_company_source(db_session)

    first_adapter = StubAdapter(
        company_slug="stripe",
        raw_jobs=[make_raw(source_job_id="1", title="Backend", location_text="Remote")],
    )
    await run_sync(
        session_factory=session_factory,
        adapter=first_adapter,
        company_id=company.id,
        source_id=source.id,
        company_source_id=cs.id,
        adapter_name="stub",
    )

    # Same source_job_id but different title → content change
    second_adapter = StubAdapter(
        company_slug="stripe",
        raw_jobs=[make_raw(source_job_id="1", title="Senior Backend", location_text="Remote")],
    )
    outcome = await run_sync(
        session_factory=session_factory,
        adapter=second_adapter,
        company_id=company.id,
        source_id=source.id,
        company_source_id=cs.id,
        adapter_name="stub",
    )

    assert outcome.jobs_new == 0
    assert outcome.jobs_updated == 1

    job = (await db_session.execute(select(Job))).scalar_one()
    await db_session.refresh(job)
    assert job.canonical_title == "Senior Backend"
    assert job.status == JobStatus.UPDATED


async def test_lifecycle_closes_after_three_missed_syncs(
    db_session: AsyncSession, session_factory: async_sessionmaker
) -> None:
    company, source, cs = await _setup_company_source(db_session)

    # Sync 1: job present
    present = StubAdapter(
        company_slug="stripe",
        raw_jobs=[make_raw(source_job_id="1", title="Backend")],
    )
    await run_sync(
        session_factory=session_factory,
        adapter=present,
        company_id=company.id,
        source_id=source.id,
        company_source_id=cs.id,
        adapter_name="stub",
    )

    # Syncs 2..N: job absent
    absent = StubAdapter(company_slug="stripe", raw_jobs=[])
    for i in range(1, CLOSE_AFTER_MISSES + 1):
        outcome = await run_sync(
            session_factory=session_factory,
            adapter=absent,
            company_id=company.id,
            source_id=source.id,
            company_source_id=cs.id,
            adapter_name="stub",
        )
        if i < CLOSE_AFTER_MISSES:
            assert outcome.jobs_closed == 0
        else:
            assert outcome.jobs_closed == 1

    job = (await db_session.execute(select(Job))).scalar_one()
    await db_session.refresh(job)
    assert job.status == JobStatus.CLOSED
    assert job.closed_at is not None
    assert job.consecutive_missed_syncs == CLOSE_AFTER_MISSES

    js = (await db_session.execute(select(JobSource))).scalar_one()
    await db_session.refresh(js)
    assert js.is_active is False


async def test_reappearing_job_reopens(
    db_session: AsyncSession, session_factory: async_sessionmaker
) -> None:
    company, source, cs = await _setup_company_source(db_session)

    present = StubAdapter(
        company_slug="stripe",
        raw_jobs=[make_raw(source_job_id="1", title="Backend")],
    )
    absent = StubAdapter(company_slug="stripe", raw_jobs=[])

    await run_sync(
        session_factory=session_factory, adapter=present, company_id=company.id,
        source_id=source.id, company_source_id=cs.id, adapter_name="stub",
    )
    for _ in range(CLOSE_AFTER_MISSES):
        await run_sync(
            session_factory=session_factory, adapter=absent, company_id=company.id,
            source_id=source.id, company_source_id=cs.id, adapter_name="stub",
        )

    # It should be CLOSED now — reappear
    outcome = await run_sync(
        session_factory=session_factory, adapter=present, company_id=company.id,
        source_id=source.id, company_source_id=cs.id, adapter_name="stub",
    )
    assert outcome.jobs_new == 0
    job = (await db_session.execute(select(Job))).scalar_one()
    await db_session.refresh(job)
    assert job.status == JobStatus.ACTIVE
    assert job.closed_at is None
    assert job.consecutive_missed_syncs == 0


async def test_pipeline_records_sync_run(
    db_session: AsyncSession, session_factory: async_sessionmaker
) -> None:
    company, source, cs = await _setup_company_source(db_session)
    adapter = StubAdapter(
        company_slug="stripe", raw_jobs=[make_raw(source_job_id="1")]
    )
    outcome = await run_sync(
        session_factory=session_factory, adapter=adapter, company_id=company.id,
        source_id=source.id, company_source_id=cs.id, adapter_name="stub",
    )

    run = await db_session.get(SyncRun, outcome.sync_run_id)
    await db_session.refresh(run)
    assert run.status == SyncRunStatus.SUCCESS
    assert run.jobs_found == 1
    assert run.jobs_new == 1
    assert run.completed_at is not None
    assert run.error is None


async def test_pipeline_records_failure(
    db_session: AsyncSession, session_factory: async_sessionmaker
) -> None:
    company, source, cs = await _setup_company_source(db_session)

    class ExplodingAdapter(StubAdapter):
        async def discover(self):
            raise RuntimeError("boom")

    adapter = ExplodingAdapter(company_slug="stripe", raw_jobs=[])
    import pytest

    with pytest.raises(RuntimeError, match="boom"):
        await run_sync(
            session_factory=session_factory, adapter=adapter, company_id=company.id,
            source_id=source.id, company_source_id=cs.id, adapter_name="stub",
        )

    run = (
        await db_session.execute(select(SyncRun).order_by(SyncRun.id.desc()).limit(1))
    ).scalar_one()
    await db_session.refresh(run)
    assert run.status == SyncRunStatus.FAILED
    assert run.error and "boom" in run.error


async def _sync_ids(session_factory, company, source, cs, ids):
    adapter = StubAdapter(
        company_slug="stripe",
        raw_jobs=[make_raw(source_job_id=str(i), title=f"Job {i}") for i in ids],
    )
    return await run_sync(
        session_factory=session_factory,
        adapter=adapter,
        company_id=company.id,
        source_id=source.id,
        company_source_id=cs.id,
        adapter_name="stub",
    )


async def test_partial_discovery_does_not_mark_misses(
    db_session: AsyncSession, session_factory: async_sessionmaker
) -> None:
    """A truncated response (Apple once served 19 of ~2,700) must not count
    as a miss for every unseen job — repeated, it would close the company."""
    company, source, cs = await _setup_company_source(db_session)
    everything = range(MIN_ACTIVE_FOR_GUARD * 2)
    await _sync_ids(session_factory, company, source, cs, everything)

    for _ in range(CLOSE_AFTER_MISSES + 1):
        outcome = await _sync_ids(session_factory, company, source, cs, range(3))
        assert outcome.jobs_closed == 0

    missed = await db_session.scalar(
        select(func.count()).select_from(Job).where(Job.consecutive_missed_syncs > 0)
    )
    assert missed == 0


async def test_normal_churn_still_closes_jobs(
    db_session: AsyncSession, session_factory: async_sessionmaker
) -> None:
    """Above the ratio, unseen jobs still accrue misses and close."""
    company, source, cs = await _setup_company_source(db_session)
    total = MIN_ACTIVE_FOR_GUARD * 2
    await _sync_ids(session_factory, company, source, cs, range(total))

    kept = range(total - 5)  # 5 postings removed — well above the ratio
    for i in range(1, CLOSE_AFTER_MISSES + 1):
        outcome = await _sync_ids(session_factory, company, source, cs, kept)
        assert outcome.jobs_closed == (5 if i == CLOSE_AFTER_MISSES else 0)


async def test_moved_application_url_is_refreshed(
    db_session: AsyncSession, session_factory: async_sessionmaker
) -> None:
    """A posting whose URL changes (e.g. an adapter host fix) must get the
    new apply link even when nothing else about the job changed."""
    company, source, cs = await _setup_company_source(db_session)
    old, new = "https://old.example/job/1", "https://new.example/job/1"
    for url in (old, new):
        await run_sync(
            session_factory=session_factory,
            adapter=StubAdapter(
                company_slug="stripe",
                raw_jobs=[make_raw(source_job_id="1", title="Backend", application_url=url)],
            ),
            company_id=company.id,
            source_id=source.id,
            company_source_id=cs.id,
            adapter_name="stub",
        )

    job = (await db_session.execute(select(Job))).scalar_one()
    await db_session.refresh(job)
    js = (await db_session.execute(select(JobSource))).scalar_one()
    await db_session.refresh(js)
    assert job.application_url == new
    assert job.canonical_url == new
    assert js.source_url == new
