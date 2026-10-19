from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_source import JobSource


class JobSourceRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_source_and_source_job_id(
        self, source_id: int, source_job_id: str
    ) -> JobSource | None:
        result = await self.session.execute(
            select(JobSource).where(
                JobSource.source_id == source_id,
                JobSource.source_job_id == source_job_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, **values) -> JobSource:
        js = JobSource(**values)
        self.session.add(js)
        await self.session.flush()
        return js
