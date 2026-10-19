"""GET /api/recommendations + match on JobDetail + sort on /api/jobs."""
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobStatus
from app.models.job_location import JobLocation
from app.models.user import User
from app.models.user_profile import UserProfile
from app.repositories.company import CompanyRepo
from app.repositories.job import JobRepo


async def _seed_user_only(db_session: AsyncSession) -> int:
    db_session.add(User(id=1, email="you@example.com"))
    await db_session.commit()
    return 1


async def _seed_user_with_profile(db_session: AsyncSession) -> int:
    user_id = await _seed_user_only(db_session)
    db_session.add(
        UserProfile(
            user_id=user_id,
            target_roles=["backend", "fullstack"],
            target_locations=["San Francisco", "Remote"],
            skills=["python", "postgres", "docker"],
            years_experience=3,
            requires_sponsorship=False,
        )
    )
    await db_session.commit()
    return user_id


async def _seed_jobs(db_session: AsyncSession):
    """Three jobs across the match spectrum."""
    acme = await CompanyRepo(db_session).create(name="Acme", slug="acme")

    strong = await JobRepo(db_session).create(
        company_id=acme.id,
        canonical_title="Senior Backend Engineer",
        description="Python, Postgres, Docker. 2+ years of experience.",
        status=JobStatus.ACTIVE,
        salary_max=Decimal("180000"),
    )
    medium = await JobRepo(db_session).create(
        company_id=acme.id,
        canonical_title="Backend Engineer",
        description="Build things.",
        status=JobStatus.ACTIVE,
        salary_max=Decimal("120000"),
    )
    poor = await JobRepo(db_session).create(
        company_id=acme.id,
        canonical_title="Product Manager",
        description="Lead a team. 10+ years experience required.",
        status=JobStatus.ACTIVE,
        salary_max=None,
    )

    db_session.add_all(
        [
            JobLocation(job_id=strong.id, location_text="San Francisco, CA", country="US"),
            JobLocation(job_id=medium.id, location_text="Remote - US"),
            JobLocation(job_id=poor.id, location_text="Berlin"),
        ]
    )
    await db_session.commit()
    return strong, medium, poor


async def test_recommendations_empty_when_no_profile(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_user_only(db_session)
    await _seed_jobs(db_session)

    response = await client.get("/api/recommendations")
    assert response.status_code == 200
    body = response.json()
    assert body == {"items": [], "total": 0, "limit": 50, "offset": 0}


async def test_recommendations_rank_strongly_matched_first(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_user_with_profile(db_session)
    strong, _medium, _poor = await _seed_jobs(db_session)

    response = await client.get(
        "/api/recommendations", params={"role_category": "any", "country": "any", "seniority": "any"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1

    first = body["items"][0]
    assert first["id"] == str(strong.id)
    assert "match" in first
    buckets = {f["bucket"] for f in first["match"]["facets"]}
    assert "strong" in buckets


async def test_job_detail_includes_match_when_profile_exists(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_user_with_profile(db_session)
    strong, *_ = await _seed_jobs(db_session)

    response = await client.get(f"/api/jobs/{strong.id}")
    body = response.json()
    assert body["match"] is not None
    keys = {f["key"] for f in body["match"]["facets"]}
    assert {"role", "location", "skills", "experience_years", "salary", "visa"} <= keys


async def test_job_detail_match_null_without_profile(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_user_only(db_session)
    strong, *_ = await _seed_jobs(db_session)

    response = await client.get(f"/api/jobs/{strong.id}")
    assert response.json()["match"] is None


async def test_jobs_list_includes_match_counts(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_user_with_profile(db_session)
    await _seed_jobs(db_session)

    response = await client.get(
        "/api/jobs", params={"role_category": "any", "country": "any", "seniority": "any"}
    )
    for item in response.json()["items"]:
        assert "match_strong_count" in item
        assert "match_gap_count" in item
        assert item["match_strong_count"] is not None


async def test_sort_by_salary_puts_nulls_last(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_user_only(db_session)
    strong, medium, poor = await _seed_jobs(db_session)

    response = await client.get(
        "/api/jobs",
        params={"sort": "salary", "role_category": "any", "country": "any", "seniority": "any"},
    )
    titles = [j["canonical_title"] for j in response.json()["items"]]
    # salary_max 180k, 120k, null — order descending with null last
    assert titles == [
        "Senior Backend Engineer",
        "Backend Engineer",
        "Product Manager",
    ]


async def test_sort_match_falls_back_to_newest_without_profile(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """When no profile exists, sort=match must silently behave like newest."""
    await _seed_user_only(db_session)
    strong, medium, poor = await _seed_jobs(db_session)

    match_resp = await client.get(
        "/api/jobs",
        params={"sort": "match", "role_category": "any", "country": "any", "seniority": "any"},
    )
    newest_resp = await client.get(
        "/api/jobs",
        params={"sort": "newest", "role_category": "any", "country": "any", "seniority": "any"},
    )
    assert match_resp.status_code == 200
    assert [j["id"] for j in match_resp.json()["items"]] == [
        j["id"] for j in newest_resp.json()["items"]
    ]


async def test_sort_match_with_profile_puts_best_first(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_user_with_profile(db_session)
    strong, medium, poor = await _seed_jobs(db_session)

    response = await client.get(
        "/api/jobs",
        params={"sort": "match", "role_category": "any", "country": "any", "seniority": "any"},
    )
    body = response.json()
    assert body["items"][0]["id"] == str(strong.id)
