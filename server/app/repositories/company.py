from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.filters import (
    company_tier_filter_expression,
    country_filter_expression,
    is_disabled,
    level_filter_expression,
    role_filter_expression,
    seniority_filter_expression,
    source_type_filter_expression,
)
from app.models.company import Company
from app.models.company_source import CompanySource
from app.models.enums import JobStatus, SourceType, SyncRunStatus
from app.models.job import Job
from app.models.sync_run import SyncRun

SortKey = Literal["name", "jobs"]


@dataclass
class CompanyWithAggregates:
    company: Company
    active_job_count: int
    last_synced_at: datetime | None


@dataclass
class JobCountFilters:
    """Filter inputs for the per-company active-job-count aggregate.

    Mirrors the shape of ``/api/jobs`` filter query params so the number
    shown on each company card tracks the sidebar filters exactly. Pass
    ``None`` (or the string ``"any"``) on any field to disable it; see
    ``app/filters/__init__.py::is_disabled``.
    """

    role_category: str | None = None
    country: str | None = None
    seniority: str | None = None
    company_tier: str | None = None
    source_types: list[SourceType] | None = None
    # Source-native career level token ("IC2", "L3", ...). Comma-separated
    # values OR together. Case-insensitive. None/"any" disables.
    level: str | None = None

    def is_noop(self) -> bool:
        """All filters disabled — equivalent to the legacy unfiltered count."""
        return (
            is_disabled(self.role_category)
            and is_disabled(self.country)
            and is_disabled(self.seniority)
            and is_disabled(self.company_tier)
            and not self.source_types
            and is_disabled(self.level)
        )


def _active_job_count_subquery(filters: JobCountFilters | None = None):
    """Correlated scalar subquery: count of ACTIVE/UPDATED jobs per outer
    company, optionally narrowed by the same filter predicates ``/api/jobs``
    composes. Correlation to ``Company`` is preserved so companies with
    zero matching rows still land in the outer result with ``count=0``."""
    stmt = (
        select(func.count(Job.id))
        .where(
            Job.company_id == Company.id,
            Job.status.in_([JobStatus.ACTIVE, JobStatus.UPDATED]),
        )
        .correlate(Company)
    )
    if filters is not None:
        if not is_disabled(filters.role_category):
            expr = role_filter_expression(filters.role_category)  # type: ignore[arg-type]
            if expr is not None:
                stmt = stmt.where(expr)
        if not is_disabled(filters.country):
            expr = country_filter_expression(filters.country)  # type: ignore[arg-type]
            if expr is not None:
                stmt = stmt.where(expr)
        if not is_disabled(filters.seniority):
            expr = seniority_filter_expression(filters.seniority)  # type: ignore[arg-type]
            if expr is not None:
                stmt = stmt.where(expr)
        if not is_disabled(filters.company_tier):
            # Raises UnknownTierError on an unknown key — caller handles.
            expr = company_tier_filter_expression(filters.company_tier)  # type: ignore[arg-type]
            if expr is not None:
                stmt = stmt.where(expr)
        if filters.source_types:
            expr = source_type_filter_expression(filters.source_types)
            if expr is not None:
                stmt = stmt.where(expr)
        if not is_disabled(filters.level):
            expr = level_filter_expression(filters.level.split(","))  # type: ignore[union-attr]
            if expr is not None:
                stmt = stmt.where(expr)
    return stmt.scalar_subquery()


def _last_synced_subquery():
    """Correlated scalar subquery: MAX(completed_at) over successful sync_runs."""
    return (
        select(func.max(SyncRun.completed_at))
        .select_from(SyncRun)
        .join(CompanySource, CompanySource.id == SyncRun.company_source_id)
        .where(
            CompanySource.company_id == Company.id,
            SyncRun.status == SyncRunStatus.SUCCESS,
        )
        .correlate(Company)
        .scalar_subquery()
    )


class CompanyRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, company_id: int) -> Company | None:
        return await self.session.get(Company, company_id)

    async def get_by_slug(self, slug: str) -> Company | None:
        result = await self.session.execute(select(Company).where(Company.slug == slug))
        return result.scalar_one_or_none()

    async def get_by_slug_with_aggregates(
        self, slug: str
    ) -> CompanyWithAggregates | None:
        active_count = _active_job_count_subquery()
        last_synced = _last_synced_subquery()

        row = (
            await self.session.execute(
                select(Company, active_count, last_synced).where(Company.slug == slug)
            )
        ).one_or_none()
        if row is None:
            return None
        company, count, last = row
        return CompanyWithAggregates(
            company=company,
            active_job_count=int(count or 0),
            last_synced_at=last,
        )

    async def list_paginated(
        self, limit: int, offset: int
    ) -> tuple[list[Company], int]:
        """Legacy no-aggregates list, kept for callers that don't need them."""
        items_result = await self.session.execute(
            select(Company).order_by(Company.id).limit(limit).offset(offset)
        )
        items = list(items_result.scalars().all())
        total = await self.session.scalar(select(func.count()).select_from(Company))
        return items, int(total or 0)

    async def list_with_aggregates(
        self,
        *,
        limit: int,
        offset: int,
        sort: SortKey = "name",
        include_inactive: bool = False,
        job_count_filters: JobCountFilters | None = None,
    ) -> tuple[list[CompanyWithAggregates], int]:
        active_count = _active_job_count_subquery(job_count_filters)
        last_synced = _last_synced_subquery()

        stmt = select(Company, active_count, last_synced)
        count_stmt = select(func.count(Company.id))

        if not include_inactive:
            stmt = stmt.where(Company.active.is_(True))
            count_stmt = count_stmt.where(Company.active.is_(True))

        if sort == "jobs":
            # Reference the subquery via its label so Postgres sorts on the
            # computed column instead of rebuilding it twice.
            stmt = stmt.order_by(active_count.desc(), Company.name.asc())
        else:
            stmt = stmt.order_by(Company.name.asc())

        stmt = stmt.limit(limit).offset(offset)

        rows = (await self.session.execute(stmt)).all()
        total = int((await self.session.scalar(count_stmt)) or 0)

        items = [
            CompanyWithAggregates(
                company=company,
                active_job_count=int(count or 0),
                last_synced_at=last,
            )
            for company, count, last in rows
        ]
        return items, total

    async def create(self, **values) -> Company:
        company = Company(**values)
        self.session.add(company)
        await self.session.flush()
        return company
