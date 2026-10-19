from decimal import Decimal

from app.ingestion.diff import diff_versions
from app.models.job_version import JobVersion


def _v(**overrides) -> JobVersion:
    defaults = dict(
        job_id=None,
        version=1,
        content_hash="h",
        title="Engineer",
        description="Build.",
        employment_type="Full-time",
        workplace_type="Remote",
        department="Engineering",
        team="Payments",
        salary_min=None,
        salary_max=None,
        salary_currency=None,
    )
    defaults.update(overrides)
    return JobVersion(**defaults)


def test_no_diff_when_fields_equal() -> None:
    assert diff_versions(_v(), _v()) == {}


def test_title_and_salary_changes_reported() -> None:
    prev = _v()
    curr = _v(
        title="Senior Engineer",
        salary_min=Decimal("150000"),
        salary_max=Decimal("200000"),
        salary_currency="USD",
    )
    changes = diff_versions(prev, curr)
    assert set(changes.keys()) == {"title", "salary_min", "salary_max", "salary_currency"}
    assert changes["title"] == {"old": "Engineer", "new": "Senior Engineer"}


def test_description_truncated_in_output() -> None:
    old = "a" * 500
    new = "b" * 500
    changes = diff_versions(_v(description=old), _v(description=new))
    assert len(changes["description"]["old"]) <= 300
    assert changes["description"]["old"].endswith("…")
