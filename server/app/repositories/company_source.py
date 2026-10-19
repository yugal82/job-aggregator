from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company_source import CompanySource


class CompanySourceRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, company_source_id: int) -> CompanySource | None:
        return await self.session.get(CompanySource, company_source_id)

    async def get_by_company_and_source(
        self, company_id: int, source_id: int
    ) -> CompanySource | None:
        result = await self.session.execute(
            select(CompanySource).where(
                CompanySource.company_id == company_id,
                CompanySource.source_id == source_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_company(self, company_id: int) -> list[CompanySource]:
        result = await self.session.execute(
            select(CompanySource).where(CompanySource.company_id == company_id)
        )
        return list(result.scalars().all())

    async def create(self, **values) -> CompanySource:
        cs = CompanySource(**values)
        self.session.add(cs)
        await self.session.flush()
        return cs
