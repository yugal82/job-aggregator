from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.job import Job
from app.models.job_source import JobSource


class JobRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, job_id: UUID) -> Job | None:
        return await self.session.get(Job, job_id)

    async def get_with_relations(self, job_id: UUID) -> Job | None:
        result = await self.session.execute(
            select(Job)
            .where(Job.id == job_id)
            .options(
                selectinload(Job.company),
                selectinload(Job.locations),
                selectinload(Job.sources).selectinload(JobSource.source),
            )
        )
        return result.scalar_one_or_none()

    async def list_paginated(
        self, limit: int, offset: int
    ) -> tuple[list[Job], int]:
        items_result = await self.session.execute(
            select(Job)
            .order_by(Job.first_seen_at.desc(), Job.id)
            .limit(limit)
            .offset(offset)
        )
        items = list(items_result.scalars().all())
        total = await self.session.scalar(select(func.count()).select_from(Job))
        return items, int(total or 0)

    async def create(self, **values) -> Job:
        job = Job(**values)
        self.session.add(job)
        await self.session.flush()
        return job
