"""Structured-level filter.

``jobs.level`` holds a source-native token (``IC2``) or a range of them
joined by ``/`` (``IC3/IC4``) when the posting spans bands. A wanted token
matches when it equals any ``/``-separated part, case-insensitively — so
``IC2`` matches both ``IC2`` and ``IC2/IC3``.
"""
from collections.abc import Iterable

from sqlalchemy import func, or_
from sqlalchemy.sql.elements import ColumnElement

from app.models.job import Job


def level_filter_expression(tokens: Iterable[str]) -> ColumnElement | None:
    wanted = [t.strip().lower() for t in tokens if t and t.strip()]
    if not wanted:
        return None
    # Wrap in delimiters so a plain substring test only hits whole parts:
    # '/ic3/ic4/' contains '/ic3/' but '/ic13/' does not.
    padded = func.concat("/", func.lower(Job.level), "/")
    return or_(*(padded.contains(f"/{t}/", autoescape=True) for t in wanted))
