from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, nulls_last, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.filters import (
    InvalidSourceTypeError,
    UnknownTierError,
    company_tier_filter_expression,
    country_filter_expression,
    is_disabled,
    parse_source_types,
    role_filter_expression,
    seniority_filter_expression,
    source_type_filter_expression,
)
from app.matching import (
    build_explanation,
    facet_counts,
    load_profile,
    match_score,
)
from app.matching.profile import has_match_signal
from app.models.company import Company
from app.models.enums import JobStatus
from app.models.job import Job
from app.models.job_location import JobLocation
from app.models.user_profile import UserProfile
from app.repositories.job import JobRepo
from app.schemas.common import Page
from app.schemas.job import JobDetail, JobSummary
from app.schemas.match import MatchExplanation

SortKey = Literal["newest", "match", "salary"]

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _apply_filters(
    stmt: Select,
    *,
    companies: list[str],
    locations: list[str],
    remote: bool | None,
    posted_after: datetime | None,
    statuses: list[JobStatus],
    q: str | None,
    role_category: str | None,
    country: str | None,
    company_tier: str | None = None,
    source_types=None,
    seniority: str | None = None,
    level: str | None = None,
) -> Select:
    if companies:
        stmt = stmt.join(Company, Company.id == Job.company_id).where(
            Company.slug.in_(companies)
        )

    if statuses:
        stmt = stmt.where(Job.status.in_(statuses))

    if posted_after is not None:
        stmt = stmt.where(Job.posted_at >= posted_after)

    if not is_disabled(role_category):
        role_expr = role_filter_expression(role_category)  # type: ignore[arg-type]
        if role_expr is not None:
            stmt = stmt.where(role_expr)

    if not is_disabled(country):
        country_expr = country_filter_expression(country)  # type: ignore[arg-type]
        if country_expr is not None:
            stmt = stmt.where(country_expr)

    # Intersect with company_tier when provided — explicit `company` and
    # `company_tier` compose by AND (predictable, documented behavior).
    if not is_disabled(company_tier):
        tier_expr = company_tier_filter_expression(company_tier)  # type: ignore[arg-type]
        if tier_expr is not None:
            stmt = stmt.where(tier_expr)

    if source_types:
        source_expr = source_type_filter_expression(source_types)
        if source_expr is not None:
            stmt = stmt.where(source_expr)

    if not is_disabled(seniority):
        sen_expr = seniority_filter_expression(seniority)  # type: ignore[arg-type]
        if sen_expr is not None:
            stmt = stmt.where(sen_expr)

    if level and level.strip().lower() not in ("any", ""):
        # Case-insensitive exact match. Comma-separated input OR's the terms
        # so a client can request `level=IC2,IC3` to widen the band.
        wanted = [t.strip().lower() for t in level.split(",") if t.strip()]
        if wanted:
            stmt = stmt.where(func.lower(Job.level).in_(wanted))

    # Location filter: "remote" is a flag match, anything else is a text match
    # against the job_locations rows. Multiple locations OR together.
    non_remote_locations = []
    wants_remote_flag = remote is True
    for loc in locations:
        if loc.lower() == "remote":
            wants_remote_flag = True
        else:
            non_remote_locations.append(loc)

    location_clauses = []
    if wants_remote_flag:
        location_clauses.append(JobLocation.remote_allowed.is_(True))
    for loc in non_remote_locations:
        pattern = f"%{loc}%"
        location_clauses.append(
            or_(
                JobLocation.location_text.ilike(pattern),
                JobLocation.city.ilike(pattern),
                JobLocation.state.ilike(pattern),
                JobLocation.country.ilike(pattern),
            )
        )

    if location_clauses:
        subquery = (
            select(JobLocation.job_id).where(or_(*location_clauses)).subquery()
        )
        stmt = stmt.where(Job.id.in_(select(subquery.c.job_id)))

    if q:
        stmt = stmt.where(
            text("jobs.search_vector @@ websearch_to_tsquery('english', :q)").bindparams(
                q=q
            )
        )

    return stmt


async def _fetch_locations_by_job(
    session: AsyncSession, job_ids: list[UUID]
) -> dict[UUID, list[JobLocation]]:
    if not job_ids:
        return {}
    rows = (
        await session.execute(
            select(JobLocation).where(JobLocation.job_id.in_(job_ids))
        )
    ).scalars().all()
    out: dict[UUID, list[JobLocation]] = {}
    for loc in rows:
        out.setdefault(loc.job_id, []).append(loc)
    return out


def _to_summaries(
    jobs: list[Job],
    explanations: dict[UUID, MatchExplanation] | None,
) -> list[JobSummary]:
    out: list[JobSummary] = []
    for job in jobs:
        summary = JobSummary.model_validate(job)
        if explanations is not None:
            exp = explanations.get(job.id)
            if exp is not None:
                strong, gap = facet_counts(exp)
                summary.match_strong_count = strong
                summary.match_gap_count = gap
        out.append(summary)
    return out


async def _paginate(
    session: AsyncSession,
    base: Select,
    *,
    limit: int,
    offset: int,
    profile: UserProfile | None = None,
    order_sql: list | None = None,
) -> Page[JobSummary]:
    """Standard SQL-ordered paginate. Match counts are added for the page items
    only (cheap)."""
    total = (
        await session.scalar(select(func.count()).select_from(base.subquery()))
    ) or 0

    ordering = order_sql if order_sql is not None else [Job.first_seen_at.desc(), Job.id]
    items = list(
        (
            await session.execute(base.order_by(*ordering).limit(limit).offset(offset))
        )
        .scalars()
        .all()
    )

    explanations: dict[UUID, MatchExplanation] | None = None
    if has_match_signal(profile):
        locations_by_job = await _fetch_locations_by_job(
            session, [j.id for j in items]
        )
        explanations = {
            j.id: build_explanation(profile, j, locations_by_job.get(j.id, []))
            for j in items
        }

    return Page[JobSummary](
        items=_to_summaries(items, explanations),
        total=int(total),
        limit=limit,
        offset=offset,
    )


async def _paginate_by_match(
    session: AsyncSession,
    base: Select,
    *,
    limit: int,
    offset: int,
    profile: UserProfile,
) -> Page[JobSummary]:
    """`sort=match` path: materialize all filtered rows, compute scores in
    Python, sort, then slice. Only used when a profile has signal — callers
    fall back to the standard path otherwise."""
    all_items = list((await session.execute(base)).scalars().all())
    total = len(all_items)
    if total == 0:
        return Page[JobSummary](items=[], total=0, limit=limit, offset=offset)

    locations_by_job = await _fetch_locations_by_job(session, [j.id for j in all_items])

    scored: list[tuple[float, Job, MatchExplanation]] = []
    for job in all_items:
        exp = build_explanation(profile, job, locations_by_job.get(job.id, []))
        scored.append((match_score(exp), job, exp))

    scored.sort(key=lambda t: (-t[0], -(t[1].first_seen_at.timestamp())))
    page = scored[offset : offset + limit]

    jobs = [j for _s, j, _e in page]
    explanations = {j.id: e for _s, j, e in page}

    return Page[JobSummary](
        items=_to_summaries(jobs, explanations),
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("", response_model=Page[JobSummary])
async def list_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    company: str | None = Query(
        default=None,
        description="Comma-separated company slugs (e.g. `stripe,airbnb`)",
    ),
    location: str | None = Query(
        default=None,
        description="Comma-separated locations. `remote` matches jobs flagged "
        "remote; everything else is matched case-insensitively against the "
        "location text / city / state / country.",
    ),
    remote: bool | None = Query(
        default=None,
        description="Shortcut for location=remote",
    ),
    posted_after: datetime | None = Query(
        default=None,
        description="Only return jobs with posted_at >= this ISO timestamp.",
    ),
    job_status: str | None = Query(
        default=None,
        alias="status",
        description="Comma-separated job statuses (DISCOVERED/ACTIVE/UPDATED/CLOSED).",
    ),
    q: str | None = Query(
        default=None,
        description="Postgres full-text search over title + description "
        "(websearch_to_tsquery syntax, e.g. `backend \"san francisco\" -junior`).",
    ),
    role_category: str = Query(
        default="swe",
        description="Role filter key from config/filters.yaml "
        "(default `swe`). Pass `any` to disable.",
    ),
    country: str = Query(
        default="US",
        description="Country filter key from config/filters.yaml "
        "(default `US`). Pass `any` to disable.",
    ),
    company_tier: str = Query(
        default="any",
        description="Curated company set from config/filters.yaml company_tiers "
        "(e.g. `big_tech`). Pass `any` to disable. Composes with `company=` "
        "via intersection.",
    ),
    source_type: str | None = Query(
        default=None,
        description="Comma-separated source types to restrict to: any of "
        "`official,ats,board`. Unset = no restriction. Jobs match if any "
        "linked source has that type.",
    ),
    seniority: str = Query(
        default="entry",
        description="Seniority filter key from config/filters.yaml "
        "(default `entry` — early-career / new-grad / L1-L3 / I-level). "
        "Pass `any` to disable.",
    ),
    level: str | None = Query(
        default=None,
        description="Source-native level token (e.g. `IC2`, `L3`, `SDE II`). "
        "Case-insensitive exact match against `jobs.level`. Comma-separated "
        "values OR together (`level=IC2,IC3`). Unset = no restriction.",
    ),
    sort: SortKey = Query(
        default="newest",
        description="`newest` (default, first_seen_at desc), `match` "
        "(server-computed match score desc; falls back to `newest` if no "
        "profile), or `salary` (salary_max desc nulls last).",
    ),
    user_id: int = Query(default=1, description="User id (single-user mode: 1)"),
    session: AsyncSession = Depends(get_session),
) -> Page[JobSummary]:
    companies = _parse_csv(company)
    locations = _parse_csv(location)

    statuses: list[JobStatus] = []
    for raw in _parse_csv(job_status):
        try:
            statuses.append(JobStatus(raw.upper()))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid status: {raw}",
            )

    try:
        source_types = parse_source_types(source_type)
    except InvalidSourceTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid source_type: {exc.bad_value}",
        )

    try:
        base = _apply_filters(
            select(Job),
            companies=companies,
            locations=locations,
            remote=remote,
            posted_after=posted_after,
            statuses=statuses,
            q=q,
            role_category=role_category,
            country=country,
            company_tier=company_tier,
            source_types=source_types,
            seniority=seniority,
            level=level,
        ).distinct()
    except UnknownTierError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown company_tier: {exc.args[0]}",
        )

    profile = await load_profile(session, user_id)

    # sort=match path: only use the match-sorted paginator when the profile
    # has signal. If no profile, silently fall back to `newest`.
    if sort == "match" and has_match_signal(profile):
        return await _paginate_by_match(
            session, base, limit=limit, offset=offset, profile=profile
        )

    order_sql: list
    if sort == "salary":
        order_sql = [nulls_last(Job.salary_max.desc()), Job.first_seen_at.desc()]
    else:  # newest, or match-with-no-profile fallback
        order_sql = [Job.first_seen_at.desc(), Job.id]

    return await _paginate(
        session,
        base,
        limit=limit,
        offset=offset,
        profile=profile,
        order_sql=order_sql,
    )


@router.get("/new", response_model=Page[JobSummary])
async def list_new_jobs(
    since: datetime | None = Query(
        default=None,
        description="Jobs with first_seen_at > since. Defaults to 24h ago.",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    role_category: str = Query(
        default="swe",
        description="Role filter key from config/filters.yaml. Pass `any` to disable.",
    ),
    country: str = Query(
        default="US",
        description="Country filter key from config/filters.yaml. Pass `any` to disable.",
    ),
    seniority: str = Query(
        default="entry",
        description="Seniority filter key from config/filters.yaml. Pass `any` to disable.",
    ),
    user_id: int = Query(default=1),
    session: AsyncSession = Depends(get_session),
) -> Page[JobSummary]:
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(hours=24)

    base = select(Job).where(Job.first_seen_at > since)

    if not is_disabled(role_category):
        role_expr = role_filter_expression(role_category)
        if role_expr is not None:
            base = base.where(role_expr)
    if not is_disabled(country):
        country_expr = country_filter_expression(country)
        if country_expr is not None:
            base = base.where(country_expr)
    if not is_disabled(seniority):
        sen_expr = seniority_filter_expression(seniority)
        if sen_expr is not None:
            base = base.where(sen_expr)

    profile = await load_profile(session, user_id)
    return await _paginate(
        session, base, limit=limit, offset=offset, profile=profile
    )


@router.get("/{job_id}", response_model=JobDetail)
async def get_job(
    job_id: UUID,
    user_id: int = Query(default=1),
    session: AsyncSession = Depends(get_session),
) -> JobDetail:
    job = await JobRepo(session).get_with_relations(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    detail = JobDetail.model_validate(job)

    profile = await load_profile(session, user_id)
    if has_match_signal(profile):
        explanation = build_explanation(profile, job, job.locations)
        detail.match = explanation
        strong, gap = facet_counts(explanation)
        detail.match_strong_count = strong
        detail.match_gap_count = gap

    return detail
