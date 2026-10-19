"""Reconcile ``config/companies.yaml`` into the ``companies`` and
``company_sources`` tables.

The YAML file is the source of truth for which companies we track and which
adapters/configuration to run against each. Running this loader is idempotent:
it upserts on natural keys (company.slug, (company_id, source_id)).

Schema:

    companies:
      - slug: stripe
        name: Stripe
        website: https://stripe.com
        careers_url: https://stripe.com/jobs
        logo_url: null
        active: true
        sources:
          - source_name: Greenhouse     # matches sources.name
            adapter: greenhouse         # registry key
            configuration:
              board_token: stripe
            enabled: true
            priority: high              # high | medium | low
"""
import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.company_source import CompanySource
from app.models.enums import SyncPriority
from app.models.source import Source

log = logging.getLogger(__name__)


class SourceLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str
    adapter: str
    configuration: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    priority: SyncPriority = SyncPriority.MEDIUM


class CompanyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str
    website: str | None = None
    careers_url: str | None = None
    logo_url: str | None = None
    active: bool = True
    sources: list[SourceLink] = Field(default_factory=list)


class ConfigFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    companies: list[CompanyEntry] = Field(default_factory=list)


class ReconcileStats(BaseModel):
    companies_created: int = 0
    companies_updated: int = 0
    links_created: int = 0
    links_updated: int = 0
    links_removed: int = 0
    unknown_sources: list[str] = Field(default_factory=list)


def load_config(path: str | Path) -> ConfigFile:
    """Load and validate a companies YAML file (no DB access)."""
    text = Path(path).read_text()
    data = yaml.safe_load(text) or {}
    return ConfigFile.model_validate(data)


async def reconcile_companies_from_yaml(
    session: AsyncSession,
    path: str | Path,
    *,
    remove_unlisted_links: bool = False,
) -> ReconcileStats:
    """Upsert everything in the YAML file into the database.

    Set ``remove_unlisted_links=True`` to also delete company_source rows that
    no longer appear in YAML (a "reconcile" in the k8s sense). Default False
    to preserve any links added out-of-band via seed/scripts.
    """
    config = load_config(path)
    stats = ReconcileStats()

    for entry in config.companies:
        company = await _upsert_company(session, entry, stats)
        listed_source_ids: set[int] = set()

        for link in entry.sources:
            source = await session.scalar(
                select(Source).where(Source.name == link.source_name)
            )
            if source is None:
                stats.unknown_sources.append(link.source_name)
                log.warning(
                    "unknown source in companies.yaml",
                    extra={"company": entry.slug, "source_name": link.source_name},
                )
                continue

            listed_source_ids.add(source.id)
            await _upsert_link(session, company, source, link, stats)

        if remove_unlisted_links:
            existing = (
                await session.execute(
                    select(CompanySource).where(CompanySource.company_id == company.id)
                )
            ).scalars().all()
            for cs in existing:
                if cs.source_id not in listed_source_ids:
                    await session.delete(cs)
                    stats.links_removed += 1

    await session.commit()
    return stats


async def _upsert_company(
    session: AsyncSession, entry: CompanyEntry, stats: ReconcileStats
) -> Company:
    company = await session.scalar(select(Company).where(Company.slug == entry.slug))
    if company is None:
        company = Company(
            slug=entry.slug,
            name=entry.name,
            website=entry.website,
            careers_url=entry.careers_url,
            logo_url=entry.logo_url,
            active=entry.active,
        )
        session.add(company)
        await session.flush()
        stats.companies_created += 1
        return company

    changed = False
    if company.name != entry.name:
        company.name = entry.name
        changed = True
    if company.website != entry.website:
        company.website = entry.website
        changed = True
    if company.careers_url != entry.careers_url:
        company.careers_url = entry.careers_url
        changed = True
    if company.logo_url != entry.logo_url:
        company.logo_url = entry.logo_url
        changed = True
    if company.active != entry.active:
        company.active = entry.active
        changed = True
    if changed:
        stats.companies_updated += 1
    return company


async def _upsert_link(
    session: AsyncSession,
    company: Company,
    source: Source,
    link: SourceLink,
    stats: ReconcileStats,
) -> None:
    existing = await session.scalar(
        select(CompanySource).where(
            CompanySource.company_id == company.id,
            CompanySource.source_id == source.id,
        )
    )
    if existing is None:
        session.add(
            CompanySource(
                company_id=company.id,
                source_id=source.id,
                adapter=link.adapter,
                configuration=link.configuration,
                enabled=link.enabled,
                priority=link.priority,
            )
        )
        stats.links_created += 1
        return

    changed = False
    if existing.adapter != link.adapter:
        existing.adapter = link.adapter
        changed = True
    if existing.configuration != link.configuration:
        existing.configuration = link.configuration
        changed = True
    if existing.enabled != link.enabled:
        existing.enabled = link.enabled
        changed = True
    if existing.priority != link.priority:
        existing.priority = link.priority
        changed = True
    if changed:
        stats.links_updated += 1
