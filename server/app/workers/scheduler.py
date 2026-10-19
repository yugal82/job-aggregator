"""Long-running scheduler process. Runs one job per enabled company_source,
firing on a cron based on the source's priority tier.

Usage:
    python -m app.workers.scheduler
"""
import asyncio
import logging
import signal
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.db import SessionLocal
from app.logging import configure_logging
from app.models.company import Company
from app.models.company_source import CompanySource
from app.models.source import Source
from app.workers.job_runner import lock_key_for, run_scheduled_sync
from app.workers.tiers import cron_for_priority

log = logging.getLogger(__name__)


async def load_targets() -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(Company, CompanySource, Source)
                .join(CompanySource, CompanySource.company_id == Company.id)
                .join(Source, CompanySource.source_id == Source.id)
                .where(
                    CompanySource.enabled.is_(True),
                    Company.active.is_(True),
                )
                .order_by(Company.slug, Source.name)
            )
        ).all()

        return [
            {
                "adapter_name": cs.adapter,
                "provider": source.provider,
                "base_url": source.base_url,
                "config": cs.configuration or {},
                "company_slug": company.slug,
                "company_id": company.id,
                "source_id": source.id,
                "company_source_id": cs.id,
                "priority": cs.priority,
            }
            for company, cs, source in rows
        ]


def schedule_all(scheduler: AsyncIOScheduler, targets: list[dict[str, Any]]) -> None:
    for target in targets:
        cron = cron_for_priority(target["priority"])
        job_id = lock_key_for(target["company_slug"], target["provider"])
        scheduler.add_job(
            run_scheduled_sync,
            trigger=CronTrigger.from_crontab(cron),
            args=[target],
            id=job_id,
            replace_existing=True,
            # If we missed the window (worker was down), skip rather than run
            # a big backlog all at once. Cron will fire us again soon.
            misfire_grace_time=300,
            # One instance per job at a time — belt to the Redis-lock suspenders.
            max_instances=1,
        )
        log.info(
            "scheduled",
            extra={
                "job_id": job_id,
                "cron": cron,
                "priority": target["priority"].value,
            },
        )


async def main() -> None:
    configure_logging()

    targets = await load_targets()
    log.info("scheduler starting", extra={"targets": len(targets)})

    scheduler = AsyncIOScheduler()
    schedule_all(scheduler, targets)
    scheduler.start()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            # Signal handlers aren't available on some platforms (e.g. Windows)
            pass

    try:
        await stop.wait()
    finally:
        scheduler.shutdown(wait=True)
        log.info("scheduler stopped")


if __name__ == "__main__":
    asyncio.run(main())
