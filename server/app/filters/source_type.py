"""Source-quality filter — restrict to jobs with at least one linked
job_sources row whose parent sources.type is in a given set."""
from sqlalchemy import select
from sqlalchemy.sql.elements import ColumnElement

from app.models.enums import SourceType
from app.models.job import Job
from app.models.job_source import JobSource
from app.models.source import Source


class InvalidSourceTypeError(ValueError):
    """Raised when a caller passes a source_type token not in SourceType."""

    def __init__(self, bad_value: str) -> None:
        super().__init__(bad_value)
        self.bad_value = bad_value


def parse_source_types(raw: str | None) -> list[SourceType] | None:
    """Parse CSV of source type names, validating each. Case-insensitive.

    Returns None when the input is None/empty (i.e. no filter requested).
    Raises InvalidSourceTypeError on an unrecognized token.
    """
    if not raw:
        return None
    tokens = [t.strip().lower() for t in raw.split(",") if t.strip()]
    if not tokens:
        return None
    out: list[SourceType] = []
    for token in tokens:
        try:
            out.append(SourceType(token))
        except ValueError as exc:
            raise InvalidSourceTypeError(token) from exc
    return out


def source_type_filter_expression(
    types: list[SourceType],
) -> ColumnElement | None:
    if not types:
        return None
    subq = (
        select(JobSource.job_id)
        .join(Source, Source.id == JobSource.source_id)
        .where(Source.type.in_(types))
    )
    return Job.id.in_(subq)
