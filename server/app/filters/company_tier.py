"""Curated company-tier filter.

A tier is just a slug list in ``config/filters.yaml``. The filter restricts
jobs to companies whose ``slug`` is in that list. Unknown slugs in the config
are logged (not fatal) by ``warn_unknown_tier_slugs`` — see app/main.py's
startup hook.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.filters.config import get_filter_config
from app.models.company import Company
from app.models.job import Job

log = logging.getLogger(__name__)


class UnknownTierError(KeyError):
    """Raised when a caller references a tier key that isn't in the config."""


def known_tiers() -> list[str]:
    return sorted(get_filter_config().company_tiers)


def company_tier_filter_expression(key: str) -> ColumnElement | None:
    tier = get_filter_config().company_tiers.get(key)
    if tier is None:
        raise UnknownTierError(key)
    if not tier.companies:
        # Empty tier matches nothing — explicit zero, not "no filter".
        return Job.company_id.in_(select(Company.id).where(Company.slug.in_([])))

    return Job.company_id.in_(
        select(Company.id).where(Company.slug.in_(tier.companies))
    )


def tiers_for_company_slug(slug: str) -> list[str]:
    """Reverse lookup: which configured tiers does this company belong to?"""
    cfg = get_filter_config()
    return sorted(
        tier_key
        for tier_key, tier in cfg.company_tiers.items()
        if slug in tier.companies
    )


async def warn_unknown_tier_slugs(session: AsyncSession) -> dict[str, list[str]]:
    """Compare each tier's slug list to the DB. Log a warning for any slug
    that doesn't match a Company row. Returns the mapping of
    ``tier_key → unknown slugs`` for callers (tests) that want to assert on it.
    """
    cfg = get_filter_config()
    if not cfg.company_tiers:
        return {}

    all_referenced = {s for t in cfg.company_tiers.values() for s in t.companies}
    if not all_referenced:
        return {}

    rows = (
        await session.execute(
            select(Company.slug).where(Company.slug.in_(all_referenced))
        )
    ).scalars().all()
    known = set(rows)

    unknown_by_tier: dict[str, list[str]] = {}
    for tier_key, tier in cfg.company_tiers.items():
        missing = [s for s in tier.companies if s not in known]
        if missing:
            unknown_by_tier[tier_key] = missing
            log.warning(
                "company_tier references unknown slugs",
                extra={"tier": tier_key, "unknown_slugs": missing},
            )
    return unknown_by_tier
