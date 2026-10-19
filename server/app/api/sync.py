from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters import build_adapter
from app.adapters.http import HTTPClient
from app.adapters.registry import AdapterNotRegisteredError
from app.db import get_session, get_session_factory
from app.ingestion.pipeline import run_sync
from app.models.company import Company
from app.models.company_source import CompanySource
from app.models.source import Source

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("/{company_id}")
async def trigger_sync(
    company_id: int,
    session: AsyncSession = Depends(get_session),
    session_factory: async_sessionmaker = Depends(get_session_factory),
) -> dict[str, Any]:
    company = await session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    rows = (
        await session.execute(
            select(CompanySource, Source)
            .join(Source, CompanySource.source_id == Source.id)
            .where(
                CompanySource.company_id == company.id,
                CompanySource.enabled.is_(True),
            )
        )
    ).all()

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No enabled sources for this company",
        )

    results: list[dict[str, Any]] = []
    for cs, source in rows:
        http = HTTPClient.for_source(source.base_url, cs.configuration)
        try:
            try:
                adapter = build_adapter(
                    provider=source.provider,
                    http=http,
                    config=cs.configuration or {},
                    company_slug=company.slug,
                )
            except AdapterNotRegisteredError as exc:
                results.append(
                    {"source": source.name, "status": "error", "error": str(exc)}
                )
                continue

            try:
                outcome = await run_sync(
                    session_factory=session_factory,
                    adapter=adapter,
                    company_id=company.id,
                    source_id=source.id,
                    company_source_id=cs.id,
                    adapter_name=cs.adapter,
                )
                results.append(
                    {
                        "source": source.name,
                        "sync_run_id": outcome.sync_run_id,
                        "status": outcome.status.value,
                        "jobs_found": outcome.jobs_found,
                        "jobs_new": outcome.jobs_new,
                        "jobs_updated": outcome.jobs_updated,
                        "jobs_closed": outcome.jobs_closed,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                results.append(
                    {"source": source.name, "status": "error", "error": str(exc)}
                )
        finally:
            await http.close()

    return {"company": company.slug, "runs": results}
