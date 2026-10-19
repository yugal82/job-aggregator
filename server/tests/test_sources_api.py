from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SourceType
from app.repositories.source import SourceRepo


async def test_list_sources(client: AsyncClient, db_session: AsyncSession) -> None:
    repo = SourceRepo(db_session)
    await repo.create(name="Greenhouse", type=SourceType.ATS, provider="greenhouse")
    await repo.create(name="Lever", type=SourceType.ATS, provider="lever")
    await db_session.commit()

    response = await client.get("/api/sources")
    assert response.status_code == 200

    body = response.json()
    assert body["total"] == 2
    types = {s["type"] for s in body["items"]}
    assert types == {"ats"}
