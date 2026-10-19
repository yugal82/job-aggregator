from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.company import CompanyRepo


async def test_list_companies_returns_seeded_rows(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    repo = CompanyRepo(db_session)
    await repo.create(name="Stripe", slug="stripe")
    await repo.create(name="OpenAI", slug="openai")
    await db_session.commit()

    response = await client.get("/api/companies")
    assert response.status_code == 200

    body = response.json()
    assert body["total"] == 2
    slugs = {c["slug"] for c in body["items"]}
    assert slugs == {"stripe", "openai"}


async def test_get_company_by_id(client: AsyncClient, db_session: AsyncSession) -> None:
    company = await CompanyRepo(db_session).create(name="Stripe", slug="stripe")
    await db_session.commit()

    response = await client.get(f"/api/companies/{company.id}")
    assert response.status_code == 200
    assert response.json()["slug"] == "stripe"


async def test_get_company_404(client: AsyncClient) -> None:
    response = await client.get("/api/companies/999999")
    assert response.status_code == 404


async def test_list_companies_pagination(client: AsyncClient, db_session: AsyncSession) -> None:
    repo = CompanyRepo(db_session)
    for i in range(5):
        await repo.create(name=f"Co {i}", slug=f"co-{i}")
    await db_session.commit()

    response = await client.get("/api/companies", params={"limit": 2, "offset": 2})
    body = response.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 2
    assert len(body["items"]) == 2
