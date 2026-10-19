"""Phase 10+: company aggregates (active_job_count, last_synced_at),
GET /api/companies/by-slug/{slug}, and the sort control on /api/companies.
"""
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company_source import CompanySource
from app.models.enums import JobStatus, SourceType, SyncRunStatus
from app.models.sync_run import SyncRun
from app.repositories.company import CompanyRepo
from app.repositories.job import JobRepo
from app.repositories.source import SourceRepo

# These aggregates tests seed title "X" with no locations, so they can't
# satisfy the swe+US+entry defaults /api/companies now applies to its
# active_job_count. Opt out everywhere by default.
NO_DEFAULTS = {"role_category": "any", "country": "any", "seniority": "any"}


async def _seed(db_session: AsyncSession):
    stripe = await CompanyRepo(db_session).create(name="Stripe", slug="stripe")
    airbnb = await CompanyRepo(db_session).create(name="Airbnb", slug="airbnb")
    quiet = await CompanyRepo(db_session).create(name="QuietCo", slug="quietco")

    gh = await SourceRepo(db_session).create(
        name="Greenhouse", type=SourceType.ATS, provider="greenhouse"
    )
    await db_session.commit()

    # Stripe: 3 ACTIVE + 1 UPDATED + 1 CLOSED + 1 DISCOVERED → active_job_count = 4
    for _ in range(3):
        await JobRepo(db_session).create(
            company_id=stripe.id, canonical_title="X", status=JobStatus.ACTIVE
        )
    await JobRepo(db_session).create(
        company_id=stripe.id, canonical_title="X", status=JobStatus.UPDATED
    )
    await JobRepo(db_session).create(
        company_id=stripe.id, canonical_title="X", status=JobStatus.CLOSED
    )
    await JobRepo(db_session).create(
        company_id=stripe.id, canonical_title="X", status=JobStatus.DISCOVERED
    )

    # Airbnb: 2 ACTIVE → active_job_count = 2
    for _ in range(2):
        await JobRepo(db_session).create(
            company_id=airbnb.id, canonical_title="Y", status=JobStatus.ACTIVE
        )

    # QuietCo: no jobs, no sync runs — active_job_count=0, last_synced_at=None

    # Link stripe to greenhouse and record two SyncRuns: one earlier success,
    # one later failed. last_synced_at should pick the earlier successful one.
    stripe_cs = CompanySource(
        company_id=stripe.id, source_id=gh.id, adapter="greenhouse",
        configuration={}, enabled=True,
    )
    airbnb_cs = CompanySource(
        company_id=airbnb.id, source_id=gh.id, adapter="greenhouse",
        configuration={}, enabled=True,
    )
    db_session.add_all([stripe_cs, airbnb_cs])
    await db_session.commit()

    now = datetime.now(timezone.utc)
    db_session.add_all([
        SyncRun(
            company_source_id=stripe_cs.id, adapter="greenhouse",
            status=SyncRunStatus.SUCCESS, started_at=now - timedelta(hours=2),
            completed_at=now - timedelta(hours=2),
        ),
        # Later failed run — must NOT count toward last_synced_at
        SyncRun(
            company_source_id=stripe_cs.id, adapter="greenhouse",
            status=SyncRunStatus.FAILED, started_at=now - timedelta(minutes=10),
            completed_at=now - timedelta(minutes=10),
        ),
        # Airbnb success — more recent than stripe's successful run
        SyncRun(
            company_source_id=airbnb_cs.id, adapter="greenhouse",
            status=SyncRunStatus.SUCCESS, started_at=now - timedelta(minutes=5),
            completed_at=now - timedelta(minutes=5),
        ),
    ])
    await db_session.commit()
    return stripe, airbnb, quiet


async def test_by_slug_returns_detail_with_both_aggregates(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    stripe, airbnb, _ = await _seed(db_session)

    response = await client.get("/api/companies/by-slug/stripe")
    assert response.status_code == 200

    body = response.json()
    assert body["slug"] == "stripe"
    assert body["id"] == stripe.id
    assert body["active_job_count"] == 4  # 3 ACTIVE + 1 UPDATED
    assert body["last_synced_at"] is not None


async def test_by_slug_404_for_unknown(client: AsyncClient) -> None:
    response = await client.get("/api/companies/by-slug/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "Company not found"}


async def test_last_synced_at_null_when_no_successful_run(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session)

    response = await client.get("/api/companies/by-slug/quietco")
    body = response.json()
    assert body["active_job_count"] == 0
    assert body["last_synced_at"] is None


async def test_last_synced_at_ignores_failed_runs(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Stripe's most recent run is FAILED — last_synced_at must pick the SUCCESS one before it."""
    stripe, airbnb, _ = await _seed(db_session)

    stripe_resp = (await client.get("/api/companies/by-slug/stripe")).json()
    airbnb_resp = (await client.get("/api/companies/by-slug/airbnb")).json()

    stripe_ts = datetime.fromisoformat(stripe_resp["last_synced_at"].replace("Z", "+00:00"))
    airbnb_ts = datetime.fromisoformat(airbnb_resp["last_synced_at"].replace("Z", "+00:00"))
    assert airbnb_ts > stripe_ts, "airbnb successful run is more recent than stripe's"


async def test_list_sort_by_jobs_orders_desc(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session)

    response = await client.get(
        "/api/companies", params={**NO_DEFAULTS, "sort": "jobs"}
    )
    body = response.json()
    slugs = [c["slug"] for c in body["items"]]
    # Stripe (4) > Airbnb (2) > QuietCo (0)
    assert slugs[:3] == ["stripe", "airbnb", "quietco"]


async def test_list_sort_by_name_default(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session)

    response = await client.get("/api/companies", params=NO_DEFAULTS)
    body = response.json()
    slugs = [c["slug"] for c in body["items"]]
    assert slugs == ["airbnb", "quietco", "stripe"]  # alphabetical


async def test_list_includes_aggregates_on_every_row(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session)

    response = await client.get("/api/companies", params=NO_DEFAULTS)
    body = response.json()
    for item in body["items"]:
        assert "active_job_count" in item
        assert "last_synced_at" in item


async def test_list_hides_inactive_by_default(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    stripe, _, _ = await _seed(db_session)
    stripe.active = False
    await db_session.commit()

    response = await client.get("/api/companies", params=NO_DEFAULTS)
    body = response.json()
    assert body["total"] == 2
    assert "stripe" not in [c["slug"] for c in body["items"]]


async def test_list_include_inactive_opt_in(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    stripe, _, _ = await _seed(db_session)
    stripe.active = False
    await db_session.commit()

    response = await client.get(
        "/api/companies", params={**NO_DEFAULTS, "include_inactive": "true"}
    )
    body = response.json()
    assert body["total"] == 3
    assert "stripe" in [c["slug"] for c in body["items"]]


async def test_get_by_id_also_carries_aggregates(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    stripe, _, _ = await _seed(db_session)

    response = await client.get(f"/api/companies/{stripe.id}")
    body = response.json()
    assert body["active_job_count"] == 4
    assert body["last_synced_at"] is not None
