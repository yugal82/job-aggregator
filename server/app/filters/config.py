"""Loader for ``config/filters.yaml``. Cached on first access."""
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "filters.yaml"
)


@dataclass(frozen=True)
class RoleCategoryRule:
    key: str
    name: str
    include_title_ilike: tuple[str, ...] = ()
    exclude_title_ilike: tuple[str, ...] = ()


@dataclass(frozen=True)
class CountryRule:
    key: str
    name: str
    country_in: tuple[str, ...] = ()
    location_text_ilike: tuple[str, ...] = ()
    location_text_regex: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompanyTier:
    key: str
    label: str
    description: str
    companies: tuple[str, ...] = ()


@dataclass(frozen=True)
class SeniorityLevelRule:
    key: str
    label: str
    description: str
    include_title_ilike: tuple[str, ...] = ()
    include_title_regex: tuple[str, ...] = ()
    exclude_title_ilike: tuple[str, ...] = ()
    exclude_title_regex: tuple[str, ...] = ()
    # Source-native level tokens that short-circuit to "match". When any
    # of these appear on ``jobs.level`` the row counts as this seniority
    # level, regardless of title heuristics. Lets Microsoft's "IC2" or
    # Google's "L3" opt into Early Career without needing the title to
    # say "new grad" / "L3" / etc. Case-insensitive at the SQL layer.
    include_levels: tuple[str, ...] = ()


@dataclass(frozen=True)
class FilterConfig:
    role_categories: dict[str, RoleCategoryRule] = field(default_factory=dict)
    countries: dict[str, CountryRule] = field(default_factory=dict)
    company_tiers: dict[str, CompanyTier] = field(default_factory=dict)
    seniority_levels: dict[str, SeniorityLevelRule] = field(default_factory=dict)


def _parse(data: dict[str, Any]) -> FilterConfig:
    role_cats = {}
    for key, cfg in (data.get("role_categories") or {}).items():
        role_cats[key] = RoleCategoryRule(
            key=key,
            name=cfg.get("name", key),
            include_title_ilike=tuple(cfg.get("include_title_ilike") or ()),
            exclude_title_ilike=tuple(cfg.get("exclude_title_ilike") or ()),
        )

    countries = {}
    for key, cfg in (data.get("countries") or {}).items():
        countries[key] = CountryRule(
            key=key,
            name=cfg.get("name", key),
            country_in=tuple(cfg.get("country_in") or ()),
            location_text_ilike=tuple(cfg.get("location_text_ilike") or ()),
            location_text_regex=tuple(cfg.get("location_text_regex") or ()),
        )

    tiers = {}
    for key, cfg in (data.get("company_tiers") or {}).items():
        tiers[key] = CompanyTier(
            key=key,
            label=cfg.get("label", key),
            description=cfg.get("description", ""),
            companies=tuple(cfg.get("companies") or ()),
        )

    seniority = {}
    for key, cfg in (data.get("seniority_levels") or {}).items():
        seniority[key] = SeniorityLevelRule(
            key=key,
            label=cfg.get("label", key),
            description=cfg.get("description", ""),
            include_title_ilike=tuple(cfg.get("include_title_ilike") or ()),
            include_title_regex=tuple(cfg.get("include_title_regex") or ()),
            exclude_title_ilike=tuple(cfg.get("exclude_title_ilike") or ()),
            exclude_title_regex=tuple(cfg.get("exclude_title_regex") or ()),
            include_levels=tuple(cfg.get("include_levels") or ()),
        )

    return FilterConfig(
        role_categories=role_cats,
        countries=countries,
        company_tiers=tiers,
        seniority_levels=seniority,
    )


_cached: FilterConfig | None = None
_cache_lock = Lock()


def get_filter_config(path: Path | None = None) -> FilterConfig:
    """Return the cached FilterConfig, loading from disk on first call.

    When ``path`` is passed (test side-channel), the loaded config becomes
    the active cache so subsequent no-arg lookups see the stubbed version.
    Callers that want to restore the default must call
    ``reload_filter_config()`` with no path (or with ``DEFAULT_CONFIG_PATH``).
    """
    global _cached
    if _cached is not None and path is None:
        return _cached
    source = path or DEFAULT_CONFIG_PATH
    with _cache_lock:
        if _cached is not None and path is None:
            return _cached
        data = yaml.safe_load(source.read_text()) or {}
        config = _parse(data)
        _cached = config
        return config


def reload_filter_config(path: Path | None = None) -> FilterConfig:
    """Force a fresh load — used by tests that stub the yaml."""
    global _cached
    with _cache_lock:
        _cached = None
    return get_filter_config(path)
