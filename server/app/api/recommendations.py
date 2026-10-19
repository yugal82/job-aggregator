"""GET /api/recommendations — ranked by server-internal match score.

Score itself never leaves the server. Items are ``RecommendedJob`` (JobSummary
plus a required ``match`` field). Returns an empty page when no profile has
been set up for the user.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.filters import (
    country_filter_expression,
    is_disabled,
    role_filter_expression,
    seniority_filter_expression,
)
from app.matching import build_explanation, facet_counts, load_profile, match_score
from app.matching.profile import has_match_signal
from app.models.job import Job
from app.models.job_location import JobLocation
from app.schemas.common import Page
from app.schemas.job import JobSummary, RecommendedJob

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


async def _fetch_locations_by_job(
    session: AsyncSession, job_ids: list
) -> dict:
    if not job_ids:
        return {}
    rows = (
        await session.execute(
            select(JobLocation).where(JobLocation.job_id.in_(job_ids))
        )
    ).scalars().all()
    out: dict = {}
    for loc in rows:
        out.setdefault(loc.job_id, []).append(loc)
    return out


@router.get("", response_model=Page[RecommendedJob])
async def list_recommendations(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user_id: int = Query(default=1),
    role_category: str = Query(
        default="swe",
        description="Role filter from config/filters.yaml. Pass `any` to disable.",
    ),
    country: str = Query(
        default="US",
        description="Country filter from config/filters.yaml. Pass `any` to disable.",
    ),
    seniority: str = Query(
        default="entry",
        description="Seniority filter from config/filters.yaml. Pass `any` to disable.",
    ),
    session: AsyncSession = Depends(get_session),
) -> Page[RecommendedJob]:
    profile = await load_profile(session, user_id)
    if not has_match_signal(profile):
        return Page[RecommendedJob](items=[], total=0, limit=limit, offset=offset)

    base = select(Job)

    if not is_disabled(role_category):
        expr = role_filter_expression(role_category)
        if expr is not None:
            base = base.where(expr)
    if not is_disabled(country):
        expr = country_filter_expression(country)
        if expr is not None:
            base = base.where(expr)
    if not is_disabled(seniority):
        expr = seniority_filter_expression(seniority)
        if expr is not None:
            base = base.where(expr)

    all_items = list((await session.execute(base.distinct())).scalars().all())
    total = len(all_items)
    if total == 0:
        return Page[RecommendedJob](items=[], total=0, limit=limit, offset=offset)

    locations_by_job = await _fetch_locations_by_job(
        session, [j.id for j in all_items]
    )

    scored = []
    for job in all_items:
        exp = build_explanation(profile, job, locations_by_job.get(job.id, []))
        scored.append((match_score(exp), job, exp))

    scored.sort(key=lambda t: (-t[0], -(t[1].first_seen_at.timestamp())))
    page = scored[offset : offset + limit]

    items: list[RecommendedJob] = []
    for _score, job, exp in page:
        strong, gap = facet_counts(exp)
        summary = JobSummary.model_validate(job)
        rec = RecommendedJob(
            **summary.model_dump(),
            match=exp,
        )
        rec.match_strong_count = strong
        rec.match_gap_count = gap
        items.append(rec)

    return Page[RecommendedJob](items=items, total=total, limit=limit, offset=offset)
