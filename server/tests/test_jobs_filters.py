"""Phase 10 filter + search tests on GET /api/jobs.

These tests isolate the behavior of specific filters (company, remote,
location, posted_after, status, FTS) and therefore disable the default
role_category/country filters.
"""
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobStatus, SourceType
from app.models.job_location import JobLocation
from app.repositories.company import CompanyRepo
from app.repositories.job import JobRepo
from app.repositories.source import SourceRepo

# Default params that opt out of the role/country filtering so each test can
# assert on the specific filter under test in isolation.
NO_DEFAULTS = {"role_category": "any", "country": "any", "seniority": "any"}


async def _two_companies_two_jobs(db_session: AsyncSession):
    stripe = await CompanyRepo(db_session).create(name="Stripe", slug="stripe")
    openai = await CompanyRepo(db_session).create(name="OpenAI", slug="openai")

    stripe_job = await JobRepo(db_session).create(
        company_id=stripe.id,
        canonical_title="Backend Engineer",
        description="Build payment systems with Python and Postgres.",
        status=JobStatus.ACTIVE,
        posted_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    openai_job = await JobRepo(db_session).create(
        company_id=openai.id,
        canonical_title="Research Engineer",
        description="Train large language models.",
        status=JobStatus.ACTIVE,
        posted_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    db_session.add_all(
        [
            JobLocation(
                job_id=stripe_job.id,
                location_text="Remote - US",
                remote_allowed=True,
            ),
            JobLocation(
                job_id=openai_job.id,
                location_text="San Francisco, CA",
                city="San Francisco",
                state="CA",
                country="US",
            ),
        ]
    )
    await db_session.commit()
    return stripe, openai, stripe_job, openai_job


async def test_filter_by_company_slug(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    stripe, openai, *_ = await _two_companies_two_jobs(db_session)

    response = await client.get("/api/jobs", params={**NO_DEFAULTS, "company": "stripe"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["company_id"] == stripe.id


async def test_filter_by_remote(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _two_companies_two_jobs(db_session)

    response = await client.get("/api/jobs", params={**NO_DEFAULTS, "remote": "true"})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["canonical_title"] == "Backend Engineer"


async def test_filter_by_location_text(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _two_companies_two_jobs(db_session)

    response = await client.get("/api/jobs", params={**NO_DEFAULTS, "location": "San Francisco"})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["canonical_title"] == "Research Engineer"


async def test_filter_by_posted_after(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _two_companies_two_jobs(db_session)

    response = await client.get(
        "/api/jobs",
        params={**NO_DEFAULTS, "posted_after": "2026-09-15T00:00:00+00:00"},
    )
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["canonical_title"] == "Research Engineer"


async def test_filter_by_status_csv(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    stripe, openai, stripe_job, openai_job = await _two_companies_two_jobs(db_session)
    openai_job.status = JobStatus.CLOSED
    await db_session.commit()

    response = await client.get("/api/jobs", params={**NO_DEFAULTS, "status": "ACTIVE"})
    assert response.json()["total"] == 1

    response = await client.get("/api/jobs", params={**NO_DEFAULTS, "status": "ACTIVE,CLOSED"})
    assert response.json()["total"] == 2


async def test_filter_by_invalid_status_returns_400(client: AsyncClient) -> None:
    response = await client.get("/api/jobs", params={**NO_DEFAULTS, "status": "WHATEVER"})
    assert response.status_code == 400


async def test_full_text_search_matches_title(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _two_companies_two_jobs(db_session)

    response = await client.get("/api/jobs", params={**NO_DEFAULTS, "q": "backend"})
    body = response.json()
    assert body["total"] == 1
    assert "Backend" in body["items"][0]["canonical_title"]


async def test_full_text_search_matches_description(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _two_companies_two_jobs(db_session)

    response = await client.get("/api/jobs", params={**NO_DEFAULTS, "q": "language models"})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["canonical_title"] == "Research Engineer"


async def test_combined_filters(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _two_companies_two_jobs(db_session)

    response = await client.get(
        "/api/jobs",
        params={**NO_DEFAULTS, "company": "stripe,openai", "remote": "true"},
    )
    body = response.json()
    # Only Stripe is flagged remote
    assert body["total"] == 1
    assert body["items"][0]["canonical_title"] == "Backend Engineer"
