"""GET /api/jobs/new (saved/applied/dismissed removed with the tracking feature)."""
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.company import CompanyRepo
from app.repositories.job import JobRepo


async def _seed_jobs(db_session: AsyncSession):
    company = await CompanyRepo(db_session).create(name="Stripe", slug="stripe")
    now = datetime.now(timezone.utc)
    j_old = await JobRepo(db_session).create(
        company_id=company.id, canonical_title="Old Role",
    )
    j_new = await JobRepo(db_session).create(
        company_id=company.id, canonical_title="New Role",
    )
    # Backdate first_seen_at on the old job so /new has something to exclude.
    j_old.first_seen_at = now - timedelta(days=3)
    j_new.first_seen_at = now - timedelta(hours=1)
    await db_session.commit()
    return j_old, j_new


async def test_new_jobs_defaults_to_last_24h(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_jobs(db_session)

    # Disable role/country defaults — this test exercises the time cutoff.
    response = await client.get(
        "/api/jobs/new",
        params={"role_category": "any", "country": "any", "seniority": "any"},
    )
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["canonical_title"] == "New Role"


async def test_new_jobs_honors_since(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_jobs(db_session)

    since = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    response = await client.get(
        "/api/jobs/new",
        params={
            "since": since,
            "role_category": "any",
            "country": "any",
            "seniority": "any",
        },
    )
    assert response.json()["total"] == 2
