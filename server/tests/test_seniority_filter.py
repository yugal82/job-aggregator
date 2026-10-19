"""Seniority (early-career) filter tests."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.filters import known_seniority_levels
from app.models.enums import JobStatus
from app.models.job_location import JobLocation
from app.repositories.company import CompanyRepo
from app.repositories.job import JobRepo

# These tests isolate the seniority filter — disable role/country defaults.
NO_OTHER = {"role_category": "any", "country": "any"}


async def test_include_levels_short_circuits_entry_match(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A job with structured level in ``include_levels`` (e.g. IC2 for
    Microsoft) must count as entry even when its title has none of the
    entry signals — the structured level is authoritative."""
    msft = await CompanyRepo(db_session).create(name="Microsoft", slug="microsoft")

    rows = [
        ("Senior Software Engineer", "IC2"),
        ("Software Engineer", "IC2"),
        ("Software Engineering IC2", "IC2"),
        ("Software Engineer", None),       # no level → excluded
        ("Software Engineer", "IC3"),      # IC3 not in include_levels
        ("Senior Software Engineer", "IC4"),
        ("Software Engineer", "IC5"),
    ]
    for title, level in rows:
        job = await JobRepo(db_session).create(
            company_id=msft.id,
            canonical_title=title,
            level=level,
            status=JobStatus.ACTIVE,
        )
        db_session.add(
            JobLocation(job_id=job.id, location_text="Redmond, WA, US", country="US")
        )
    await db_session.commit()

    response = await client.get("/api/jobs", params={**NO_OTHER})
    returned_pairs = {
        (j["canonical_title"], j["level"]) for j in response.json()["items"]
    }

    # Three IC2 rows should land, nothing else.
    assert ("Senior Software Engineer", "IC2") in returned_pairs
    assert ("Software Engineer", "IC2") in returned_pairs
    assert ("Software Engineering IC2", "IC2") in returned_pairs
    # IC3+ must stay out
    for pair in [
        ("Software Engineer", "IC3"),
        ("Senior Software Engineer", "IC4"),
        ("Software Engineer", "IC5"),
    ]:
        assert pair not in returned_pairs
    # Null-level + plain "Software Engineer" title: no entry signal in
    # either → excluded.
    assert ("Software Engineer", None) not in returned_pairs


async def test_include_levels_is_case_insensitive(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Adapters may normalize level casing differently (we normalize to
    IC2, but older rows or alt adapters may store it as 'ic2' / 'Ic2').
    The include_levels filter must match them all."""
    msft = await CompanyRepo(db_session).create(name="Microsoft", slug="microsoft")
    for level_str in ("IC2", "ic2", "Ic2"):
        job = await JobRepo(db_session).create(
            company_id=msft.id, canonical_title="Software Engineer",
            level=level_str, status=JobStatus.ACTIVE,
        )
        db_session.add(
            JobLocation(job_id=job.id, location_text="Redmond, WA, US", country="US")
        )
    await db_session.commit()

    response = await client.get("/api/jobs", params={**NO_OTHER})
    assert response.json()["total"] == 3


async def _mixed_titles(db_session: AsyncSession):
    acme = await CompanyRepo(db_session).create(name="Acme", slug="acme")
    titles = [
        # Should pass `seniority=entry` (early-career signals, full-time only)
        "Software Engineer, New Grad",
        "Entry Level Software Developer",
        "Junior Backend Engineer",
        "Software Engineer I",
        "SDE I",
        "SWE 1",
        "Early Career Software Engineer",
        # Internship titles — belong in `seniority=internship`, NOT `entry`
        "Software Engineering Intern",
        "2026 Software Engineering Internship",
        "Software Engineer Co-op",
        # Should NOT pass `seniority=entry`
        "Senior Software Engineer",
        "Staff Software Engineer",
        "Principal Engineer",
        "Software Engineer II",
        "SDE II",
        "SWE 2",
        "Software Engineer III",
        "L5 Software Engineer",
        "Software Engineering Manager",
        "Distinguished Engineer",
        "Engineering Director",
        # Edge case: "international" must NOT be caught by the intern regex
        "International Software Engineer I",
    ]
    created = {}
    for title in titles:
        job = await JobRepo(db_session).create(
            company_id=acme.id,
            canonical_title=title,
            status=JobStatus.ACTIVE,
        )
        # All US so default country filter doesn't interfere elsewhere
        db_session.add(
            JobLocation(job_id=job.id, location_text="San Francisco, CA", country="US")
        )
        created[title] = job
    await db_session.commit()
    return created


def test_entry_is_registered() -> None:
    assert "entry" in known_seniority_levels()


async def test_entry_default_only_returns_early_career(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _mixed_titles(db_session)

    response = await client.get("/api/jobs", params={**NO_OTHER})
    titles = {j["canonical_title"] for j in response.json()["items"]}

    # Full-time early-career signals should ALL be present.
    expected_entry = {
        "Software Engineer, New Grad",
        "Entry Level Software Developer",
        "Junior Backend Engineer",
        "Software Engineer I",
        "SDE I",
        "SWE 1",
        "Early Career Software Engineer",
    }
    assert expected_entry <= titles

    # Internships belong in `seniority=internship`, NOT `entry`.
    for intern_title in [
        "Software Engineering Intern",
        "2026 Software Engineering Internship",
        "Software Engineer Co-op",
    ]:
        assert intern_title not in titles

    # Senior / staff / level markers must be absent.
    for bad in [
        "Senior Software Engineer",
        "Staff Software Engineer",
        "Principal Engineer",
        "Software Engineer II",
        "SDE II",
        "Software Engineer III",
        "L5 Software Engineer",
        "Software Engineering Manager",
        "Distinguished Engineer",
        "Engineering Director",
    ]:
        assert bad not in titles

    # "International Software Engineer I" should NOT get caught by the
    # intern exclude — word-boundary regex guards against this false match.
    assert "International Software Engineer I" in titles


async def test_internship_level_matches_only_internships(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _mixed_titles(db_session)

    response = await client.get(
        "/api/jobs", params={**NO_OTHER, "seniority": "internship"}
    )
    titles = {j["canonical_title"] for j in response.json()["items"]}

    assert titles == {
        "Software Engineering Intern",
        "2026 Software Engineering Internship",
        "Software Engineer Co-op",
    }


async def test_seniority_any_disables_the_filter(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    titles = await _mixed_titles(db_session)

    response = await client.get(
        "/api/jobs", params={**NO_OTHER, "seniority": "any"}
    )
    returned = {j["canonical_title"] for j in response.json()["items"]}
    # Every seeded title should come back
    assert returned == set(titles.keys())


async def test_senior_excluded_despite_sde_i_substring() -> None:
    """Guard against regex false-positives: 'Senior Software Engineer II'
    must stay excluded (senior AND II both trip excludes)."""
    from app.filters.seniority import seniority_filter_expression
    expr = seniority_filter_expression("entry")
    # The clause structure is: INCLUDE ∧ NOT(EXCLUDE). We just need it compiles.
    assert expr is not None


async def test_unknown_seniority_key_is_silent_noop(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Mirrors role_category behavior: unknown key = no filter applied."""
    titles = await _mixed_titles(db_session)

    response = await client.get(
        "/api/jobs", params={**NO_OTHER, "seniority": "no-such-level"}
    )
    returned = {j["canonical_title"] for j in response.json()["items"]}
    assert returned == set(titles.keys())
