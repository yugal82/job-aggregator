from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.canonical_url import select_canonical_url
from app.ingestion.persister import create_job, update_job
from app.models.enums import SourceType
from app.models.job import Job
from app.repositories.company import CompanyRepo
from app.repositories.source import SourceRepo
from tests._stub_adapter import StubAdapter, make_raw


async def _setup(db_session: AsyncSession):
    company = await CompanyRepo(db_session).create(name="Stripe", slug="stripe")
    official = await SourceRepo(db_session).create(
        name="StripeCareers", type=SourceType.OFFICIAL, provider="stripe-official"
    )
    ats = await SourceRepo(db_session).create(
        name="Greenhouse", type=SourceType.ATS, provider="greenhouse"
    )
    board = await SourceRepo(db_session).create(
        name="LinkedIn", type=SourceType.BOARD, provider="linkedin"
    )
    await db_session.commit()
    return company, official, ats, board


async def test_canonical_url_prefers_official_over_ats_over_board(
    db_session: AsyncSession,
) -> None:
    company, official, ats, board = await _setup(db_session)
    adapter = StubAdapter(company_slug="stripe", raw_jobs=[])

    # Start by ingesting from the BOARD source — it's the only option.
    board_canonical = adapter.normalize(
        make_raw(source_job_id="1", title="Backend", application_url="https://linkedin.com/jobs/1")
    )
    job = await create_job(db_session, board_canonical, company_id=company.id, source_id=board.id)
    await db_session.commit()
    assert job.canonical_url == "https://linkedin.com/jobs/1"

    # Now the ATS source arrives — same role (same fingerprint will match in L4).
    ats_canonical = adapter.normalize(
        make_raw(
            source_job_id="2",
            title="Backend",
            application_url="https://boards.greenhouse.io/stripe/jobs/2",
        )
    )
    await update_job(db_session, job, ats_canonical, source_id=ats.id)
    await db_session.commit()
    await db_session.refresh(job)
    assert job.canonical_url == "https://boards.greenhouse.io/stripe/jobs/2"

    # Finally the OFFICIAL source arrives — must win over ATS.
    official_canonical = adapter.normalize(
        make_raw(
            source_job_id="3",
            title="Backend",
            application_url="https://stripe.com/jobs/3",
        )
    )
    await update_job(db_session, job, official_canonical, source_id=official.id)
    await db_session.commit()
    await db_session.refresh(job)
    assert job.canonical_url == "https://stripe.com/jobs/3"


async def test_select_canonical_url_returns_none_when_no_sources(
    db_session: AsyncSession,
) -> None:
    import uuid

    assert await select_canonical_url(db_session, uuid.uuid4()) is None
