"""Compute a shallow diff between two JobVersion snapshots."""
from typing import Any

from app.models.job_version import JobVersion

_DIFFABLE_FIELDS: tuple[str, ...] = (
    "title",
    "description",
    "employment_type",
    "workplace_type",
    "department",
    "team",
    "salary_min",
    "salary_max",
    "salary_currency",
)

# Description can be huge; truncate before reporting so the diff stays loggable.
_DESCRIPTION_SNIPPET_LEN = 240


def _value_for_diff(field: str, value: Any) -> Any:
    if field == "description" and isinstance(value, str) and len(value) > _DESCRIPTION_SNIPPET_LEN:
        return value[:_DESCRIPTION_SNIPPET_LEN] + "…"
    return value


def diff_versions(
    previous: JobVersion, current: JobVersion
) -> dict[str, dict[str, Any]]:
    """Return ``{field: {"old": prev, "new": curr}}`` for every differing field.

    Returns an empty dict if nothing changed in the diffable set.
    """
    changes: dict[str, dict[str, Any]] = {}
    for field in _DIFFABLE_FIELDS:
        old = getattr(previous, field)
        new = getattr(current, field)
        if old != new:
            changes[field] = {
                "old": _value_for_diff(field, old),
                "new": _value_for_diff(field, new),
            }
    return changes
