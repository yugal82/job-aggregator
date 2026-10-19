import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobStatus
from app.repositories.company import CompanyRepo
from app.repositories.job import JobRepo


async def test_list_jobs_paginates(client: AsyncClient, db_session: AsyncSession) -> None:
    company = await CompanyRepo(db_session).create(name="Stripe", slug="stripe")
    job_repo = JobRepo(db_session)
    for i in range(4):
        await job_repo.create(
            company_id=company.id, canonical_title=f"Engineer {i}", status=JobStatus.ACTIVE
        )
    await db_session.commit()

    # Disable role/country defaults — this test exercises pagination, not filters.
    response = await client.get(
        "/api/jobs",
        params={
            "limit": 2,
            "offset": 0,
            "role_category": "any",
            "country": "any",
            "seniority": "any",
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 4
    assert len(body["items"]) == 2


async def test_get_job_detail_includes_company(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    company = await CompanyRepo(db_session).create(name="Stripe", slug="stripe")
    job = await JobRepo(db_session).create(
        company_id=company.id,
        canonical_title="Backend Engineer",
        description="Build things",
        status=JobStatus.ACTIVE,
    )
    await db_session.commit()

    response = await client.get(f"/api/jobs/{job.id}")
    assert response.status_code == 200

    body = response.json()
    assert body["canonical_title"] == "Backend Engineer"
    assert body["description"] == "Build things"
    assert body["company"]["slug"] == "stripe"
    assert body["locations"] == []


async def test_get_job_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/jobs/{uuid.uuid4()}")
    assert response.status_code == 404
