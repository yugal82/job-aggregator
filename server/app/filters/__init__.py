"""Config-driven filter rules for /api/jobs.

Rules live in ``config/filters.yaml``. Importers call ``*_filter_expression``
to get a SQLAlchemy predicate, or ``None`` when the key isn't defined.

Pass ``key == "any"`` (or any falsy value) on query params to short-circuit.
"""
from app.filters.company_tier import (
    UnknownTierError,
    company_tier_filter_expression,
    known_tiers,
    tiers_for_company_slug,
    warn_unknown_tier_slugs,
)
from app.filters.config import FilterConfig, get_filter_config, reload_filter_config
from app.filters.country import country_filter_expression, known_countries
from app.filters.level import level_filter_expression
from app.filters.role import known_role_categories, role_filter_expression
from app.filters.seniority import known_seniority_levels, seniority_filter_expression
from app.filters.source_type import (
    InvalidSourceTypeError,
    parse_source_types,
    source_type_filter_expression,
)

ANY = "any"


def is_disabled(value: str | None) -> bool:
    """Query-param convention: empty, 'any', or 'all' disables the filter."""
    if not value:
        return True
    return value.strip().lower() in {ANY, "all", "*"}


__all__ = [
    "ANY",
    "FilterConfig",
    "InvalidSourceTypeError",
    "UnknownTierError",
    "company_tier_filter_expression",
    "country_filter_expression",
    "get_filter_config",
    "is_disabled",
    "known_countries",
    "known_role_categories",
    "known_seniority_levels",
    "known_tiers",
    "level_filter_expression",
    "parse_source_types",
    "reload_filter_config",
    "role_filter_expression",
    "seniority_filter_expression",
    "source_type_filter_expression",
    "tiers_for_company_slug",
    "warn_unknown_tier_slugs",
]
