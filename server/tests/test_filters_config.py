"""Role-category + country filter rules (config-driven)."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.filters import known_countries, known_role_categories
from app.models.enums import JobStatus
from app.models.job_location import JobLocation
from app.repositories.company import CompanyRepo
from app.repositories.job import JobRepo

# These tests exercise role_category + country specifically; the seeded
# titles aren't entry-level, so the seniority default must be opted out.
SENIORITY_OFF = {"seniority": "any"}


async def _mixed_corpus(db_session: AsyncSession):
    """Seeds a representative mix: SWE/non-SWE × US/non-US."""
    acme = await CompanyRepo(db_session).create(name="Acme", slug="acme")

    rows: list[tuple[str, str | None]] = [
        # SWE titles
        ("Backend Engineer", "New York, NY"),         # SWE / US
        ("Software Engineer, Payments", "San Francisco, CA"),  # SWE / US
        ("Senior Engineer - Platform", "London"),      # SWE / non-US
        ("Mobile Developer", "Dublin"),                # SWE / non-US
        ("Full Stack Engineer", "Remote - US"),        # SWE / US (remote)
        # Non-SWE titles even if "engineer" appears
        ("Hardware Engineer", "San Jose, CA"),         # non-SWE / US
        ("Sales Engineer", "New York, NY"),            # non-SWE / US
        ("Security Engineer", "Austin, TX"),           # non-SWE (by exclude rule) / US
        # Not engineering at all
        ("Product Manager", "San Francisco, CA"),      # non-SWE / US
        ("Technical Program Manager", "Seattle, WA"),  # non-SWE / US
        ("Tax Analyst", "New York, NY"),               # non-SWE / US
        # Canada should NOT be picked up by the state-code regex despite "CA"
        ("Backend Engineer", "Toronto, Canada"),       # SWE / non-US
    ]
    jobs = []
    for title, loc in rows:
        job = await JobRepo(db_session).create(
            company_id=acme.id,
            canonical_title=title,
            status=JobStatus.ACTIVE,
        )
        jobs.append(job)
        if loc:
            db_session.add(
                JobLocation(
                    job_id=job.id,
                    location_text=loc,
                    remote_allowed="remote" in loc.lower(),
                )
            )
    await db_session.commit()
    return jobs


def test_known_categories_includes_swe() -> None:
    assert "swe" in known_role_categories()


def test_known_countries_includes_us() -> None:
    assert "US" in known_countries()


async def test_defaults_apply_swe_and_us(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _mixed_corpus(db_session)

    response = await client.get("/api/jobs", params=SENIORITY_OFF)
    body = response.json()

    titles = {j["canonical_title"] for j in body["items"]}
    # Only SWE titles in US locations should remain:
    assert titles == {
        "Backend Engineer",
        "Software Engineer, Payments",
        "Full Stack Engineer",
    }


async def test_role_any_disables_role_filter(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _mixed_corpus(db_session)

    response = await client.get(
        "/api/jobs", params={**SENIORITY_OFF, "role_category": "any", "country": "US"}
    )
    titles = {j["canonical_title"] for j in response.json()["items"]}
    # All US jobs (SWE + non-SWE), no non-US
    assert titles == {
        "Backend Engineer",
        "Software Engineer, Payments",
        "Full Stack Engineer",
        "Hardware Engineer",
        "Sales Engineer",
        "Security Engineer",
        "Product Manager",
        "Technical Program Manager",
        "Tax Analyst",
    }


async def test_country_any_disables_country_filter(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _mixed_corpus(db_session)

    response = await client.get(
        "/api/jobs", params={**SENIORITY_OFF, "role_category": "swe", "country": "any"}
    )
    titles = {j["canonical_title"] for j in response.json()["items"]}
    # All SWE titles, regardless of country. Two "Backend Engineer" jobs share
    # a title (one US, one Canada) — set collapses them.
    assert titles == {
        "Backend Engineer",
        "Software Engineer, Payments",
        "Senior Engineer - Platform",
        "Mobile Developer",
        "Full Stack Engineer",
    }
    assert response.json()["total"] == 6  # SWE jobs across both countries


async def test_security_engineer_is_excluded_from_swe(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _mixed_corpus(db_session)
    response = await client.get("/api/jobs", params=SENIORITY_OFF)
    titles = {j["canonical_title"] for j in response.json()["items"]}
    assert "Security Engineer" not in titles
    assert "Sales Engineer" not in titles
    assert "Hardware Engineer" not in titles


async def test_chip_design_titles_are_excluded_from_swe(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Chip/silicon engineering roles — ASIC, VLSI, physical design, SerDes,
    mixed-signal, hardware verification — slip in via the broad ``engineer,``
    include patterns. These are hardware, not software; keep them out of swe."""
    chipco = await CompanyRepo(db_session).create(name="ChipCo", slug="chipco")
    hardware_titles = [
        "ASIC Design Engineer",
        "ASIC Verification Engineer",
        "ASIC Physical Design Engineer, Netlisting",
        "VLSI Physical Design Engineer",
        "GPU Verification Engineer",
        "Hardware Design Validation Engineer",
        "High Speed SerDes Validation Engineer",
        "Mixed Signal Design Engineer",
        "Formal Verification Engineer",
        "RTL Design Engineer",
        "Silicon Design Engineer",
        "Semiconductor Device Engineer",
    ]
    software_titles = [
        "Software Engineer, DL Kernel Libraries",
        "Deep Learning Software Engineer, TensorRT",
        "C++ Software Engineer, Infrastructure Tools",
        "Systems Software Engineer, AI and Cloud",
        "Machine Learning Engineer, Perception",
        # DevTech == software at Nvidia; the ", " triggers %engineer, % include
        "Developer Technology Engineer, Public Sector",
    ]
    for title in hardware_titles + software_titles:
        job = await JobRepo(db_session).create(
            company_id=chipco.id, canonical_title=title, status=JobStatus.ACTIVE
        )
        db_session.add(
            JobLocation(job_id=job.id, location_text="Santa Clara, CA", country="US")
        )
    await db_session.commit()

    response = await client.get("/api/jobs", params=SENIORITY_OFF)
    titles = {j["canonical_title"] for j in response.json()["items"]}

    for hw in hardware_titles:
        assert hw not in titles, f"hardware title leaked: {hw}"
    for sw in software_titles:
        assert sw in titles, f"software title wrongly excluded: {sw}"


async def test_canada_not_matched_as_us(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The ', CA' pattern must only match the state code California, not Canada."""
    await _mixed_corpus(db_session)
    response = await client.get("/api/jobs", params={**SENIORITY_OFF, "role_category": "any"})

    # The Toronto SWE job must not appear when country=US is applied.
    toronto_present = any(
        j.get("canonical_title") == "Backend Engineer"
        and "Toronto" in (j.get("location_text") or "")
        for j in response.json()["items"]
    )
    assert not toronto_present


async def test_unknown_category_is_silently_skipped(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A role_category key that isn't in the yaml should be a no-op, not a 500."""
    await _mixed_corpus(db_session)
    response = await client.get(
        "/api/jobs",
        params={**SENIORITY_OFF, "role_category": "no-such-category", "country": "any"},
    )
    assert response.status_code == 200
    # No filter applied → all 12 jobs returned
    assert response.json()["total"] == 12
