"""Country filter — builds a SQLAlchemy predicate against the job's locations.

A job matches if ANY of its job_location rows satisfies any configured rule
(country column IN, location_text ILIKE, or case-sensitive location_text regex).
Jobs with no location rows do NOT match any country — this is intentional:
if the data doesn't say where a role lives, we don't claim it's in the US.
"""
from sqlalchemy import or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.filters.config import get_filter_config
from app.models.job import Job
from app.models.job_location import JobLocation


def country_filter_expression(key: str) -> ColumnElement | None:
    rule = get_filter_config().countries.get(key)
    if rule is None:
        return None

    clauses: list[ColumnElement] = []
    if rule.country_in:
        clauses.append(JobLocation.country.in_(rule.country_in))

    for pattern in rule.location_text_ilike:
        clauses.append(JobLocation.location_text.ilike(pattern))

    # Postgres case-sensitive regex (~). Needed for 2-letter US state codes
    # since ILIKE would collide with the start of other words (e.g. "Canada").
    for pattern in rule.location_text_regex:
        clauses.append(JobLocation.location_text.op("~")(pattern))

    if not clauses:
        return None

    matching_job_ids = select(JobLocation.job_id).where(or_(*clauses))
    return Job.id.in_(matching_job_ids)


def known_countries() -> list[str]:
    return sorted(get_filter_config().countries)
