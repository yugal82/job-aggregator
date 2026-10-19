from app.adapters.models import CanonicalJob, CanonicalLocation
from app.ingestion.fingerprint import compute_fingerprint


def _job(
    title: str = "Senior Backend Engineer",
    description: str | None = "Build systems.",
    location: str | None = "Remote",
) -> CanonicalJob:
    locations = [CanonicalLocation(location_text=location)] if location else []
    return CanonicalJob(
        company_slug="x",
        source_provider="stub",
        source_job_id="1",
        title=title,
        description=description,
        locations=locations,
        raw_data={},
        content_hash="",
    )


def test_identical_jobs_produce_identical_fingerprint() -> None:
    assert compute_fingerprint(_job()) == compute_fingerprint(_job())


def test_whitespace_and_punctuation_variations_match() -> None:
    a = _job(title="Senior Backend Engineer", location="San Francisco, CA")
    b = _job(title="  SENIOR!! backend-engineer ", location="san francisco  ca")
    assert compute_fingerprint(a) == compute_fingerprint(b)


def test_different_titles_differ() -> None:
    assert compute_fingerprint(_job(title="Backend Engineer")) != compute_fingerprint(
        _job(title="Frontend Engineer")
    )


def test_description_cap_limits_influence() -> None:
    base = "a " * 500  # first ~800 chars dominate
    a = _job(description=base + "unique suffix one")
    b = _job(description=base + "different suffix two")
    # Suffixes land beyond the cap → fingerprints match
    assert compute_fingerprint(a) == compute_fingerprint(b)


def test_missing_fields_still_hashable() -> None:
    fp = compute_fingerprint(_job(description=None, location=None))
    assert isinstance(fp, str) and len(fp) == 64
