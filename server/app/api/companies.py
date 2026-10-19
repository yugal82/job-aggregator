from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.filters import (
    InvalidSourceTypeError,
    UnknownTierError,
    parse_source_types,
    tiers_for_company_slug,
)
from app.repositories.company import (
    CompanyRepo,
    CompanyWithAggregates,
    JobCountFilters,
    SortKey,
)
from app.schemas.common import Page
from app.schemas.company import CompanyResponse

router = APIRouter(prefix="/api/companies", tags=["companies"])


def _to_response(bundle: CompanyWithAggregates) -> CompanyResponse:
    """Fold the (company, active_job_count, last_synced_at) tuple into the schema."""
    return CompanyResponse.model_validate(bundle.company).model_copy(
        update={
            "active_job_count": bundle.active_job_count,
            "last_synced_at": bundle.last_synced_at,
            "tiers": tiers_for_company_slug(bundle.company.slug),
        }
    )


@router.get("", response_model=Page[CompanyResponse])
async def list_companies(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: SortKey = Query(
        default="name",
        description="Sort order: `name` ascending (default), or `jobs` for "
        "active_job_count descending with name as the tiebreaker.",
    ),
    include_inactive: bool = Query(
        default=False,
        description="Include companies with active=false. Default hides them.",
    ),
    # Filter params — these mirror /api/jobs exactly so the per-card
    # active_job_count matches /api/jobs?company=<slug>&... total for every
    # company in the response. Companies with zero matching rows still
    # appear (with active_job_count=0) so the sidebar can toggle them on.
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
    seniority: str = Query(
        default="entry",
        description="Seniority filter key (default `entry`). Pass `any` to disable.",
    ),
    company_tier: str = Query(
        default="any",
        description="Curated company set from company_tiers (e.g. `big_tech`). "
        "Pass `any` to disable.",
    ),
    source_type: str | None = Query(
        default=None,
        description="Comma-separated source types: any of `official,ats,board`. "
        "Unset = no restriction.",
    ),
    level: str | None = Query(
        default=None,
        description="Source-native level token (e.g. `IC2`, `L3`). "
        "Case-insensitive exact match. Comma-separated values OR together. "
        "Unset = no restriction.",
    ),
    session: AsyncSession = Depends(get_session),
) -> Page[CompanyResponse]:
    try:
        source_types = parse_source_types(source_type)
    except InvalidSourceTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid source_type: {exc.bad_value}",
        )

    filters = JobCountFilters(
        role_category=role_category,
        country=country,
        seniority=seniority,
        company_tier=company_tier,
        source_types=source_types,
        level=level,
    )

    try:
        items, total = await CompanyRepo(session).list_with_aggregates(
            limit=limit,
            offset=offset,
            sort=sort,
            include_inactive=include_inactive,
            job_count_filters=filters,
        )
    except UnknownTierError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown company_tier: {exc.args[0]}",
        )

    return Page[CompanyResponse](
        items=[_to_response(b) for b in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/by-slug/{slug}", response_model=CompanyResponse)
async def get_company_by_slug(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> CompanyResponse:
    bundle = await CompanyRepo(session).get_by_slug_with_aggregates(slug)
    if bundle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
        )
    return _to_response(bundle)


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: int,
    session: AsyncSession = Depends(get_session),
) -> CompanyResponse:
    company = await CompanyRepo(session).get(company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    # Reuse the by-slug aggregates path so this endpoint carries them too —
    # saves clients from issuing a second query when they already have the id.
    bundle = await CompanyRepo(session).get_by_slug_with_aggregates(company.slug)
    assert bundle is not None  # we just fetched it
    return _to_response(bundle)
