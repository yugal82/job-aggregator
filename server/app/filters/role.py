"""Role-category filter — builds a SQLAlchemy predicate against Job.canonical_title."""
from sqlalchemy import and_, not_, or_
from sqlalchemy.sql.elements import ColumnElement

from app.filters.config import get_filter_config
from app.models.job import Job


def role_filter_expression(key: str) -> ColumnElement | None:
    """Return a boolean SQL expression constraining Job.canonical_title to a
    role category, or ``None`` if the key isn't registered.

    Semantics: title must match ANY include pattern AND NONE of the excludes.
    """
    rule = get_filter_config().role_categories.get(key)
    if rule is None:
        return None

    include_clauses = [Job.canonical_title.ilike(p) for p in rule.include_title_ilike]
    exclude_clauses = [Job.canonical_title.ilike(p) for p in rule.exclude_title_ilike]

    if not include_clauses:
        return None

    include_expr = or_(*include_clauses)
    if exclude_clauses:
        return and_(include_expr, not_(or_(*exclude_clauses)))
    return include_expr


def known_role_categories() -> list[str]:
    return sorted(get_filter_config().role_categories)
