import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.companies import router as companies_router
from app.api.filters import router as filters_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.metrics import router as metrics_router
from app.api.recommendations import router as recommendations_router
from app.api.sources import router as sources_router
from app.api.sync import router as sync_router
from app.config.settings import get_settings
from app.db import SessionLocal
from app.filters import warn_unknown_tier_slugs
from app.logging import configure_logging

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup: validate company_tiers configuration against the DB.
    # Any tier slug that doesn't match a Company row is logged but doesn't
    # fail boot — unknown slugs are silently skipped at query time.
    try:
        async with SessionLocal() as session:
            await warn_unknown_tier_slugs(session)
    except Exception:  # noqa: BLE001
        log.warning("company_tier config validation skipped (DB unavailable)")
    yield


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Job Aggregator API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(companies_router)
    app.include_router(sources_router)
    app.include_router(jobs_router)
    app.include_router(recommendations_router)
    app.include_router(filters_router)
    app.include_router(sync_router)
    return app


app = create_app()
