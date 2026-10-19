from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.dedupe import find_matching_job
from app.ingestion.persister import create_job
from app.models.enums import SourceType
from app.repositories.company import CompanyRepo
from app.repositories.source import SourceRepo
from tests._stub_adapter import StubAdapter, make_raw


async def _setup(db_session: AsyncSession):
    company = await CompanyRepo(db_session).create(name="Stripe", slug="stripe")
    source = await SourceRepo(db_session).create(
        name="Greenhouse", type=SourceType.ATS, provider="greenhouse"
    )
    await db_session.commit()
    return company, source


async def test_l1_source_id_match(db_session: AsyncSession) -> None:
    company, source = await _setup(db_session)
    adapter = StubAdapter(company_slug="stripe", raw_jobs=[])
    canonical = adapter.normalize(make_raw(source_job_id="ABC"))
    await create_job(db_session, canonical, company_id=company.id, source_id=source.id)
    await db_session.commit()

    match = await find_matching_job(
        db_session,
        adapter.normalize(make_raw(source_job_id="ABC")),
        company_id=company.id,
        source_id=source.id,
    )
    assert match is not None
    assert match.canonical_title == "Engineer"


async def test_l2_requisition_id_match(db_session: AsyncSession) -> None:
    company, source = await _setup(db_session)
    adapter = StubAdapter(company_slug="stripe", raw_jobs=[])

    # existing job with requisition_id set, from a different source_job_id
    canonical = adapter.normalize(make_raw(source_job_id="OLD", requisition_id="R-100"))
    await create_job(db_session, canonical, company_id=company.id, source_id=source.id)
    await db_session.commit()

    # incoming job has a new source_job_id but the same requisition_id
    incoming = adapter.normalize(make_raw(source_job_id="NEW", requisition_id="R-100"))
    match = await find_matching_job(
        db_session, incoming, company_id=company.id, source_id=source.id
    )
    assert match is not None
    assert match.requisition_id == "R-100"


async def test_l3_url_match_after_stripping_utm(db_session: AsyncSession) -> None:
    company, source = await _setup(db_session)
    adapter = StubAdapter(company_slug="stripe", raw_jobs=[])
    canonical = adapter.normalize(
        make_raw(source_job_id="OLD", application_url="https://stripe.com/jobs/1?utm_source=x")
    )
    await create_job(db_session, canonical, company_id=company.id, source_id=source.id)
    await db_session.commit()

    incoming = adapter.normalize(
        make_raw(source_job_id="NEW", application_url="https://stripe.com/jobs/1?utm_medium=email")
    )
    match = await find_matching_job(
        db_session, incoming, company_id=company.id, source_id=source.id
    )
    assert match is not None
    assert match.canonical_url == "https://stripe.com/jobs/1"


async def test_no_match_returns_none(db_session: AsyncSession) -> None:
    company, source = await _setup(db_session)
    adapter = StubAdapter(company_slug="stripe", raw_jobs=[])
    match = await find_matching_job(
        db_session,
        adapter.normalize(make_raw(source_job_id="ANY")),
        company_id=company.id,
        source_id=source.id,
    )
    assert match is None
