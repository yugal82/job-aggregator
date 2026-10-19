"""Command-line entry points.

Usage:
    python -m app.cli sync --company stripe
    python -m app.cli sync --company all
    python -m app.cli reconcile-config [--path config/companies.yaml]
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

from sqlalchemy import select

from app.adapters import build_adapter
from app.adapters.http import HTTPClient
from app.config.loader import reconcile_companies_from_yaml
from app.db import SessionLocal
from app.ingestion.pipeline import run_sync
from app.logging import configure_logging
from app.models.company import Company
from app.models.company_source import CompanySource
from app.models.source import Source

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "companies.yaml"


async def _load_targets(company_slug: str | None) -> list[dict]:
    """Snapshot the (company, company_source, source) rows to sync.

    Returns a list of plain dicts so the caller can close the DB session
    before running per-source syncs in their own transactions.
    """
    async with SessionLocal() as session:
        query = (
            select(Company, CompanySource, Source)
            .join(CompanySource, CompanySource.company_id == Company.id)
            .join(Source, CompanySource.source_id == Source.id)
            .where(CompanySource.enabled.is_(True), Company.active.is_(True))
            .order_by(Company.slug, Source.name)
        )
        if company_slug and company_slug != "all":
            query = query.where(Company.slug == company_slug)

        rows = (await session.execute(query)).all()

        if not rows and company_slug and company_slug != "all":
            # Distinguish "no company by that slug" from "no enabled sources"
            exists = await session.scalar(
                select(Company.id).where(Company.slug == company_slug)
            )
            if exists is None:
                raise SystemExit(
                    f"company '{company_slug}' not found — "
                    "try `python -m app.cli reconcile-config`"
                )
            raise SystemExit(f"no enabled sources for '{company_slug}'")

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
                "source_name": source.name,
            }
            for company, cs, source in rows
        ]


async def _sync_one(target: dict) -> bool:
    """Run one source sync. Returns False on failure (already logged)."""
    log.info(
        "sync starting",
        extra={
            "company": target["company_slug"],
            "provider": target["provider"],
            "adapter": target["adapter_name"],
        },
    )

    http = HTTPClient.for_source(target["base_url"], target["config"])
    try:
        try:
            adapter = build_adapter(
                provider=target["provider"],
                http=http,
                config=target["config"],
                company_slug=target["company_slug"],
            )
            outcome = await run_sync(
                session_factory=SessionLocal,
                adapter=adapter,
                company_id=target["company_id"],
                source_id=target["source_id"],
                company_source_id=target["company_source_id"],
                adapter_name=target["adapter_name"],
            )
            print(
                f"[{target['company_slug']}/{target['source_name']}] "
                f"{outcome.status.value}: found={outcome.jobs_found} "
                f"new={outcome.jobs_new} updated={outcome.jobs_updated} "
                f"closed={outcome.jobs_closed} (sync_run_id={outcome.sync_run_id})"
            )
            return True
        except Exception as exc:  # noqa: BLE001
            # Adapter isolation: don't let one broken source kill the batch.
            log.exception(
                "sync failed",
                extra={
                    "company": target["company_slug"],
                    "provider": target["provider"],
                },
            )
            print(
                f"[{target['company_slug']}/{target['source_name']}] "
                f"failed: {type(exc).__name__}: {exc}"
            )
            return False
    finally:
        await http.close()


async def sync_company(company_slug: str) -> bool:
    """Sync every target; one failure doesn't stop the rest. Returns
    False if any target failed so the CLI can exit non-zero."""
    targets = await _load_targets(company_slug)
    if not targets:
        print("no enabled company_sources to sync")
        return True
    results = [await _sync_one(target) for target in targets]
    return all(results)


async def reconcile_config(path: Path) -> None:
    async with SessionLocal() as session:
        stats = await reconcile_companies_from_yaml(session, path)
    print(
        f"companies: +{stats.companies_created} created, "
        f"~{stats.companies_updated} updated | "
        f"links: +{stats.links_created} created, "
        f"~{stats.links_updated} updated"
    )
    if stats.unknown_sources:
        print(
            f"warning: unknown source names referenced in YAML: "
            f"{sorted(set(stats.unknown_sources))}"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.cli", description="Job Aggregator CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sync = sub.add_parser("sync", help="Run the ingestion pipeline")
    sync.add_argument(
        "--company",
        required=True,
        help="company slug (e.g. stripe) or 'all' for every enabled source",
    )

    reconcile = sub.add_parser("reconcile-config", help="Sync companies.yaml → DB")
    reconcile.add_argument(
        "--path",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"path to companies.yaml (default: {DEFAULT_CONFIG_PATH})",
    )

    return parser


def main() -> None:
    configure_logging()
    args = _build_parser().parse_args()

    if args.cmd == "sync":
        if not asyncio.run(sync_company(args.company)):
            # Non-zero so a failed source shows red in GitHub Actions.
            sys.exit(1)
    elif args.cmd == "reconcile-config":
        asyncio.run(reconcile_config(Path(args.path)))


if __name__ == "__main__":
    main()
