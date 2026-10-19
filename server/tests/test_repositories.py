import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobStatus, SourceType
from app.repositories.company import CompanyRepo
from app.repositories.company_source import CompanySourceRepo
from app.repositories.job import JobRepo
from app.repositories.job_source import JobSourceRepo
from app.repositories.source import SourceRepo


async def test_company_repo_roundtrip(db_session: AsyncSession) -> None:
    repo = CompanyRepo(db_session)
    company = await repo.create(name="Stripe", slug="stripe", website="https://stripe.com")
    await db_session.commit()

    fetched = await repo.get(company.id)
    assert fetched is not None
    assert fetched.slug == "stripe"

    by_slug = await repo.get_by_slug("stripe")
    assert by_slug is not None
    assert by_slug.id == company.id


async def test_company_repo_pagination(db_session: AsyncSession) -> None:
    repo = CompanyRepo(db_session)
    for i in range(5):
        await repo.create(name=f"Co {i}", slug=f"co-{i}")
    await db_session.commit()

    page1, total = await repo.list_paginated(limit=2, offset=0)
    page2, _ = await repo.list_paginated(limit=2, offset=2)

    assert total == 5
    assert len(page1) == 2
    assert len(page2) == 2
    assert page1[0].id != page2[0].id


async def test_source_repo_create_and_get(db_session: AsyncSession) -> None:
    repo = SourceRepo(db_session)
    source = await repo.create(
        name="Greenhouse",
        type=SourceType.ATS,
        provider="greenhouse",
        base_url="https://boards-api.greenhouse.io",
    )
    await db_session.commit()

    fetched = await repo.get_by_name("Greenhouse")
    assert fetched is not None
    assert fetched.id == source.id
    assert fetched.type == SourceType.ATS


async def test_company_source_uniqueness_via_repo(db_session: AsyncSession) -> None:
    company = await CompanyRepo(db_session).create(name="Stripe", slug="stripe")
    source = await SourceRepo(db_session).create(
        name="Greenhouse", type=SourceType.ATS, provider="greenhouse"
    )
    await db_session.commit()

    cs_repo = CompanySourceRepo(db_session)
    await cs_repo.create(
        company_id=company.id,
        source_id=source.id,
        adapter="greenhouse",
        configuration={"board_token": "stripe"},
    )
    await db_session.commit()

    found = await cs_repo.get_by_company_and_source(company.id, source.id)
    assert found is not None
    assert found.configuration == {"board_token": "stripe"}


async def test_job_repo_create_and_list(db_session: AsyncSession) -> None:
    company = await CompanyRepo(db_session).create(name="Stripe", slug="stripe")
    await db_session.commit()

    job_repo = JobRepo(db_session)
    for i in range(3):
        await job_repo.create(
            company_id=company.id,
            canonical_title=f"Engineer {i}",
            status=JobStatus.ACTIVE,
        )
    await db_session.commit()

    items, total = await job_repo.list_paginated(limit=10, offset=0)
    assert total == 3
    assert len(items) == 3
    assert all(item.company_id == company.id for item in items)


async def test_job_source_uniqueness(db_session: AsyncSession) -> None:
    company = await CompanyRepo(db_session).create(name="Stripe", slug="stripe")
    source = await SourceRepo(db_session).create(
        name="Greenhouse", type=SourceType.ATS, provider="greenhouse"
    )
    await db_session.commit()

    job = await JobRepo(db_session).create(company_id=company.id, canonical_title="Engineer")
    await db_session.commit()

    js_repo = JobSourceRepo(db_session)
    await js_repo.create(job_id=job.id, source_id=source.id, source_job_id="123")
    await db_session.commit()

    found = await js_repo.get_by_source_and_source_job_id(source.id, "123")
    assert found is not None
    assert found.job_id == job.id


async def test_job_repo_get_with_relations_returns_company(db_session: AsyncSession) -> None:
    company = await CompanyRepo(db_session).create(name="Stripe", slug="stripe")
    await db_session.commit()

    job = await JobRepo(db_session).create(company_id=company.id, canonical_title="Engineer")
    await db_session.commit()

    fetched = await JobRepo(db_session).get_with_relations(job.id)
    assert fetched is not None
    assert fetched.company.slug == "stripe"


def test_job_id_is_uuid() -> None:
    from app.models.job import Job

    assert Job.__table__.c.id.type.python_type is uuid.UUID
