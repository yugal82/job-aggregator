from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.repositories.source import SourceRepo
from app.schemas.common import Page
from app.schemas.source import SourceResponse

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("", response_model=Page[SourceResponse])
async def list_sources(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> Page[SourceResponse]:
    items, total = await SourceRepo(session).list_paginated(limit=limit, offset=offset)
    return Page[SourceResponse](
        items=[SourceResponse.model_validate(s) for s in items],
        total=total,
        limit=limit,
        offset=offset,
    )
