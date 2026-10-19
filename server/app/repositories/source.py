from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source import Source


class SourceRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, source_id: int) -> Source | None:
        return await self.session.get(Source, source_id)

    async def get_by_name(self, name: str) -> Source | None:
        result = await self.session.execute(select(Source).where(Source.name == name))
        return result.scalar_one_or_none()

    async def list_paginated(
        self, limit: int, offset: int
    ) -> tuple[list[Source], int]:
        items_result = await self.session.execute(
            select(Source).order_by(Source.id).limit(limit).offset(offset)
        )
        items = list(items_result.scalars().all())
        total = await self.session.scalar(select(func.count()).select_from(Source))
        return items, int(total or 0)

    async def create(self, **values) -> Source:
        source = Source(**values)
        self.session.add(source)
        await self.session.flush()
        return source
