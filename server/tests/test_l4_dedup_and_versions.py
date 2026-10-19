from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ingestion.dedupe import find_matching_job
from app.ingestion.pipeline import run_sync
from app.models.company_source import CompanySource
from app.models.enums import SourceType
from app.models.job import Job
from app.models.job_version import JobVersion
from app.repositories.company import CompanyRepo
from app.repositories.source import SourceRepo
from tests._stub_adapter import StubAdapter, make_raw


async def _setup(db_session: AsyncSession):
    company = await CompanyRepo(db_session).create(name="Stripe", slug="stripe")
    source_a = await SourceRepo(db_session).create(
        name="ATS A", type=SourceType.ATS, provider="stub-a"
    )
    source_b = await SourceRepo(db_session).create(
        name="ATS B", type=SourceType.BOARD, provider="stub-b"
    )
    cs_a = CompanySource(
        company_id=company.id, source_id=source_a.id, adapter="stub-a",
        configuration={}, enabled=True,
    )
    cs_b = CompanySource(
        company_id=company.id, source_id=source_b.id, adapter="stub-b",
        configuration={}, enabled=True,
    )
    db_session.add_all([cs_a, cs_b])
    await db_session.commit()
    return company, source_a, cs_a, source_b, cs_b


async def test_l4_fingerprint_matches_across_sources(
    db_session: AsyncSession, session_factory: async_sessionmaker
) -> None:
    company, source_a, cs_a, source_b, cs_b = await _setup(db_session)

    # Source A sees the role first — different source_job_id, different URL, no requisition_id
    adapter_a = StubAdapter(
        company_slug="stripe",
        raw_jobs=[make_raw(source_job_id="A1", title="Senior Backend Engineer",
                           location_text="Remote", application_url="https://a.example/jobs/A1")],
    )
    await run_sync(
        session_factory=session_factory, adapter=adapter_a, company_id=company.id,
        source_id=source_a.id, company_source_id=cs_a.id, adapter_name="stub-a",
    )

    # Source B sees what's clearly the same role (same title + location + description)
    # but a different source_job_id and URL. L1/L2/L3 all miss — L4 fingerprint should match.
    adapter_b = StubAdapter(
        company_slug="stripe",
        raw_jobs=[make_raw(source_job_id="B99", title="Senior Backend Engineer",
                           location_text="Remote", application_url="https://b.example/jobs/B99")],
    )
    outcome = await run_sync(
        session_factory=session_factory, adapter=adapter_b, company_id=company.id,
        source_id=source_b.id, company_source_id=cs_b.id, adapter_name="stub-b",
    )
    assert outcome.jobs_new == 0  # L4 matched → not a new job

    # One canonical job with two active job_sources
    total_jobs = await db_session.scalar(select(func.count()).select_from(Job))
    assert total_jobs == 1
    job = (await db_session.execute(select(Job))).scalar_one()
    await db_session.refresh(job, attribute_names=["sources"])
    assert {js.source_id for js in job.sources} == {source_a.id, source_b.id}


async def test_create_writes_version_one_and_change_appends(
    db_session: AsyncSession, session_factory: async_sessionmaker
) -> None:
    company, source_a, cs_a, *_ = await _setup(db_session)

    adapter_v1 = StubAdapter(
        company_slug="stripe",
        raw_jobs=[make_raw(source_job_id="1", title="Engineer", location_text="Remote")],
    )
    await run_sync(
        session_factory=session_factory, adapter=adapter_v1, company_id=company.id,
        source_id=source_a.id, company_source_id=cs_a.id, adapter_name="stub-a",
    )

    versions = (await db_session.execute(select(JobVersion))).scalars().all()
    assert len(versions) == 1
    assert versions[0].version == 1
    assert versions[0].title == "Engineer"

    # Re-run with identical content — no new version expected
    await run_sync(
        session_factory=session_factory, adapter=adapter_v1, company_id=company.id,
        source_id=source_a.id, company_source_id=cs_a.id, adapter_name="stub-a",
    )
    count = await db_session.scalar(select(func.count()).select_from(JobVersion))
    assert count == 1

    # Change the title (hence content_hash) → new version row
    adapter_v2 = StubAdapter(
        company_slug="stripe",
        raw_jobs=[make_raw(source_job_id="1", title="Senior Engineer", location_text="Remote")],
    )
    await run_sync(
        session_factory=session_factory, adapter=adapter_v2, company_id=company.id,
        source_id=source_a.id, company_source_id=cs_a.id, adapter_name="stub-a",
    )
    versions = (
        await db_session.execute(select(JobVersion).order_by(JobVersion.version))
    ).scalars().all()
    assert [v.version for v in versions] == [1, 2]
    assert versions[1].title == "Senior Engineer"


async def test_l4_direct_lookup(db_session: AsyncSession) -> None:
    """Sanity check: compute_fingerprint-derived L4 match works via find_matching_job."""
    from app.ingestion.persister import create_job

    company = await CompanyRepo(db_session).create(name="Stripe", slug="stripe")
    source = await SourceRepo(db_session).create(
        name="ATS", type=SourceType.ATS, provider="stub-x"
    )
    await db_session.commit()

    adapter = StubAdapter(company_slug="stripe", raw_jobs=[])
    existing = adapter.normalize(make_raw(source_job_id="X", title="Backend"))
    await create_job(db_session, existing, company_id=company.id, source_id=source.id)
    await db_session.commit()

    # Different source_job_id but same normalized title → L4 should match.
    incoming = adapter.normalize(make_raw(source_job_id="Y", title=" backend!! "))
    match = await find_matching_job(
        db_session, incoming, company_id=company.id, source_id=source.id
    )
    assert match is not None


async def test_l4_multiple_matches_picks_lowest_id(
    db_session: AsyncSession,
) -> None:
    """When two existing jobs share a fingerprint (near-template preview text
    across siblings), L4 must not crash — pick the lowest-id row so re-syncs
    behave deterministically."""
    from app.ingestion.persister import create_job

    company = await CompanyRepo(db_session).create(name="Apple", slug="apple")
    source = await SourceRepo(db_session).create(
        name="AppleCareers", type=SourceType.OFFICIAL, provider="stub-apple"
    )
    await db_session.commit()

    adapter = StubAdapter(company_slug="apple", raw_jobs=[])
    # Two jobs with same title + description + no location → identical
    # fingerprint. (compute_fingerprint ignores source_job_id.)
    first = adapter.normalize(make_raw(source_job_id="A", title="Specialist"))
    second = adapter.normalize(make_raw(source_job_id="B", title="Specialist"))
    await create_job(db_session, first, company_id=company.id, source_id=source.id)
    await create_job(db_session, second, company_id=company.id, source_id=source.id)
    await db_session.commit()

    # A fresh canonical with the same fingerprint should map to the first one
    # (lowest id), not raise MultipleResultsFound.
    incoming = adapter.normalize(make_raw(source_job_id="C", title="Specialist"))
    match = await find_matching_job(
        db_session, incoming, company_id=company.id, source_id=source.id
    )
    assert match is not None
    first_row = (
        await db_session.execute(
            select(Job).where(Job.company_id == company.id).order_by(Job.id).limit(1)
        )
    ).scalar_one()
    assert match.id == first_row.id
