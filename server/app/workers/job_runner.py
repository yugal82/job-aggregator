"""Runs a single scheduled sync with distributed locking + metrics."""
import logging
import time
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.adapters import build_adapter
from app.adapters.http import HTTPClient
from app.db import SessionLocal
from app.ingestion.pipeline import run_sync
from app.observability.metrics import (
    JOBS_FETCHED_TOTAL,
    SOURCE_FAILURES_TOTAL,
    SYNC_DURATION_SECONDS,
    SYNC_SKIPPED_TOTAL,
)
from app.services.sync_lock import SyncLock

log = logging.getLogger(__name__)


def lock_key_for(company_slug: str, provider: str) -> str:
    return f"sync:{company_slug}:{provider}"


async def run_scheduled_sync(
    target: dict[str, Any],
    *,
    lock_ttl_seconds: int = 3600,  # retained for signature compat; advisory lock has no TTL
    session_factory: async_sessionmaker | None = None,
) -> None:
    """Fires from APScheduler. Never re-raises — a broken adapter must not
    take the scheduler down.

    ``session_factory`` is injectable for tests; defaults to the app's
    production ``SessionLocal``. ``lock_ttl_seconds`` is accepted but
    unused — Postgres advisory locks are session-scoped (auto-released on
    connection drop), so no explicit TTL is needed.
    """
    del lock_ttl_seconds  # kept for callers; see docstring

    if session_factory is None:
        session_factory = SessionLocal

    company_slug = target["company_slug"]
    provider = target["provider"]
    labels = {"provider": provider, "company": company_slug}

    lock = SyncLock(lock_key_for(company_slug, provider))
    started = time.monotonic()

    try:
        if not await lock.acquire():
            SYNC_SKIPPED_TOTAL.labels(**labels).inc()
            log.info("sync skipped — lock held by another worker", extra=labels)
            return

        http = HTTPClient(base_url=target["base_url"] or "")
        try:
            adapter = build_adapter(
                provider=provider,
                http=http,
                config=target["config"],
                company_slug=company_slug,
            )
            outcome = await run_sync(
                session_factory=session_factory,
                adapter=adapter,
                company_id=target["company_id"],
                source_id=target["source_id"],
                company_source_id=target["company_source_id"],
                adapter_name=target["adapter_name"],
            )
            JOBS_FETCHED_TOTAL.labels(**labels).inc(outcome.jobs_found)
            log.info(
                "scheduled sync completed",
                extra={
                    **labels,
                    "status": outcome.status.value,
                    "found": outcome.jobs_found,
                    "new": outcome.jobs_new,
                    "updated": outcome.jobs_updated,
                    "closed": outcome.jobs_closed,
                },
            )
        except Exception as exc:  # noqa: BLE001
            SOURCE_FAILURES_TOTAL.labels(**labels, reason=type(exc).__name__).inc()
            log.exception("scheduled sync failed", extra=labels)
        finally:
            await http.close()
    finally:
        SYNC_DURATION_SECONDS.labels(**labels).observe(time.monotonic() - started)
        await lock.release()
