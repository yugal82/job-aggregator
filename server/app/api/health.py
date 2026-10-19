"""Public probes.

``/health``  — cheap liveness check (returns 200 as soon as the ASGI app
                is up). Vercel + hosting providers hit this for readiness
                gating; keep it instant and dependency-free.

``/ready``   — pings the DB. Deploy pipelines gate release on this.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception:
        return {"status": "degraded", "database": "error"}
