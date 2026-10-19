"""Seniority-level filter.

A job matches a seniority level when its ``canonical_title`` satisfies
*any* include pattern AND *none* of the exclude patterns. Both ILIKE
(for literal substrings) and case-insensitive regex (`~*`, for level
markers like ``II`` / ``L5`` that need word boundaries) are supported.

In addition, ``include_levels`` lets a seniority rule short-circuit
to "match" when ``jobs.level`` carries a source-native token like
``IC2`` / ``L3`` / ``SDE I``. The structured level overrides title
heuristics: a Microsoft ``IC2`` role whose title says "Senior Software
Engineer" still counts as Early Career because MSFT's structured level
is authoritative. Semantics:

    MATCH = (title_match AND NOT title_exclude)  OR  (any level part IN include_levels)
"""
from sqlalchemy import and_, not_, or_
from sqlalchemy.sql.elements import ColumnElement

from app.filters.config import get_filter_config
from app.filters.level import level_filter_expression
from app.models.job import Job


def seniority_filter_expression(key: str) -> ColumnElement | None:
    rule = get_filter_config().seniority_levels.get(key)
    if rule is None:
        return None

    include_clauses: list[ColumnElement] = []
    for pattern in rule.include_title_ilike:
        include_clauses.append(Job.canonical_title.ilike(pattern))
    for pattern in rule.include_title_regex:
        include_clauses.append(Job.canonical_title.op("~*")(pattern))

    exclude_clauses: list[ColumnElement] = []
    for pattern in rule.exclude_title_ilike:
        exclude_clauses.append(Job.canonical_title.ilike(pattern))
    for pattern in rule.exclude_title_regex:
        exclude_clauses.append(Job.canonical_title.op("~*")(pattern))

    title_match: ColumnElement | None = None
    if include_clauses:
        include_expr = or_(*include_clauses)
        if exclude_clauses:
            title_match = and_(include_expr, not_(or_(*exclude_clauses)))
        else:
            title_match = include_expr

    # Structured-level short-circuit; ranges like ``IC2/IC3`` count too.
    level_match = level_filter_expression(rule.include_levels)

    if title_match is not None and level_match is not None:
        return or_(title_match, level_match)
    return title_match if title_match is not None else level_match


def known_seniority_levels() -> list[str]:
    return sorted(get_filter_config().seniority_levels)
