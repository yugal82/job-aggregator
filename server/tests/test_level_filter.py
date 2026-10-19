"""`/api/jobs?level=` and parity on `/api/companies?level=`.

Semantic contract:
    /api/companies?level=X.counts[slug] == /api/jobs?company=slug&level=X.total
"""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobStatus
from app.models.job_location import JobLocation
from app.repositories.company import CompanyRepo
from app.repositories.job import JobRepo

NO_DEFAULTS = {"role_category": "any", "country": "any", "seniority": "any"}


async def _seed_leveled(db_session: AsyncSession):
    acme = await CompanyRepo(db_session).create(name="Acme", slug="acme")

    rows = [
        ("Software Engineer", "IC2"),
        ("Software Engineer, Payments", "IC2"),
        ("Senior Software Engineer", "IC4"),
        ("Staff Software Engineer", "IC5"),
        ("Software Engineer, Platform", None),  # no level
    ]
    for title, level in rows:
        job = await JobRepo(db_session).create(
            company_id=acme.id,
            canonical_title=title,
            level=level,
            status=JobStatus.ACTIVE,
        )
        db_session.add(
            JobLocation(job_id=job.id, location_text="Redmond, WA, US", country="US")
        )
    await db_session.commit()
    return acme


async def test_level_exact_match_is_case_insensitive(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_leveled(db_session)
    for probe in ("IC2", "ic2", "iC2"):
        response = await client.get(
            "/api/jobs", params={**NO_DEFAULTS, "level": probe}
        )
        assert response.status_code == 200
        assert response.json()["total"] == 2, f"expected 2 for level={probe}"


async def test_level_csv_ors_terms(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_leveled(db_session)
    response = await client.get(
        "/api/jobs", params={**NO_DEFAULTS, "level": "IC2,IC4"}
    )
    assert response.json()["total"] == 3  # 2 IC2 + 1 IC4


async def test_level_omitted_returns_everything(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Dropping the param matches the pre-filter behavior — every active row."""
    await _seed_leveled(db_session)
    response = await client.get("/api/jobs", params=NO_DEFAULTS)
    assert response.json()["total"] == 5


async def test_level_any_opts_out(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_leveled(db_session)
    response = await client.get(
        "/api/jobs", params={**NO_DEFAULTS, "level": "any"}
    )
    assert response.json()["total"] == 5


async def test_unknown_level_returns_zero(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A level that doesn't exist in the DB is a valid filter — returns 0,
    not a 400."""
    await _seed_leveled(db_session)
    response = await client.get(
        "/api/jobs", params={**NO_DEFAULTS, "level": "IC99"}
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0


async def test_companies_count_tracks_jobs_total(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Semantic parity: /api/companies card count == /api/jobs total for
    the same filter query."""
    await _seed_leveled(db_session)

    companies_resp = await client.get(
        "/api/companies", params={**NO_DEFAULTS, "level": "IC2"}
    )
    counts = {c["slug"]: c["active_job_count"] for c in companies_resp.json()["items"]}
    assert counts.get("acme") == 2

    jobs_resp = await client.get(
        "/api/jobs", params={**NO_DEFAULTS, "level": "IC2", "company": "acme"}
    )
    assert jobs_resp.json()["total"] == counts["acme"]


async def test_summary_response_includes_level(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Client needs to render the level token — must come back on list items."""
    await _seed_leveled(db_session)
    response = await client.get(
        "/api/jobs", params={**NO_DEFAULTS, "level": "IC2"}
    )
    for item in response.json()["items"]:
        assert item["level"] == "IC2"


async def test_level_matches_any_part_of_a_range(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """MSFT postings can span bands (`IC2/IC3`). Each part is matchable on
    its own, but only whole parts — `IC2` must not hit `IC12`."""
    acme = await CompanyRepo(db_session).create(name="Acme", slug="acme")
    for title, level in [
        ("Software Engineer", "IC2/IC3"),
        ("Software Engineer II", "IC3/IC4"),
        ("Principal Engineer", "IC12"),
    ]:
        await JobRepo(db_session).create(
            company_id=acme.id, canonical_title=title, level=level,
            status=JobStatus.ACTIVE,
        )
    await db_session.commit()

    async def total(level: str) -> int:
        resp = await client.get("/api/jobs", params={**NO_DEFAULTS, "level": level})
        return resp.json()["total"]

    assert await total("IC2") == 1
    assert await total("ic3") == 2
    assert await total("IC2/IC3") == 1  # the exact stored range still matches
    assert await total("IC1") == 0


async def test_entry_seniority_includes_ic2_ranges(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """`seniority=entry` (include_levels: IC2) picks up `IC2/IC3` postings
    whose title alone wouldn't qualify."""
    acme = await CompanyRepo(db_session).create(name="Acme", slug="acme")
    await JobRepo(db_session).create(
        company_id=acme.id, canonical_title="Senior Software Engineer",
        level="IC2/IC3", status=JobStatus.ACTIVE,
    )
    await JobRepo(db_session).create(
        company_id=acme.id, canonical_title="Senior Software Engineer",
        level="IC4/IC5", status=JobStatus.ACTIVE,
    )
    await db_session.commit()

    resp = await client.get(
        "/api/jobs",
        params={"role_category": "any", "country": "any", "seniority": "entry"},
    )
    assert [j["level"] for j in resp.json()["items"]] == ["IC2/IC3"]
