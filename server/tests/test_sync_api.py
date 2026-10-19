from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import JobSourceAdapter
from app.adapters.registry import _REGISTRY  # test-only introspection
from app.models.company_source import CompanySource
from app.models.enums import SourceType
from app.models.sync_run import SyncRun
from app.repositories.company import CompanyRepo
from app.repositories.source import SourceRepo


class NoopAdapter(JobSourceAdapter):
    """Registry-compatible adapter that discovers zero jobs."""

    provider = "noop"

    async def discover(self):
        return []

    async def get_job(self, source_job_id):  # pragma: no cover
        raise LookupError(source_job_id)

    def normalize(self, raw):  # pragma: no cover
        raise NotImplementedError


async def test_sync_returns_404_for_unknown_company(client: AsyncClient) -> None:
    response = await client.post("/api/sync/999999")
    assert response.status_code == 404


async def test_sync_returns_400_when_no_enabled_sources(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    company = await CompanyRepo(db_session).create(name="Stripe", slug="stripe")
    await db_session.commit()

    response = await client.post(f"/api/sync/{company.id}")
    assert response.status_code == 400


async def test_sync_runs_registered_adapter(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    company = await CompanyRepo(db_session).create(name="Stripe", slug="stripe")
    source = await SourceRepo(db_session).create(
        name="NoopSource", type=SourceType.ATS, provider="noop"
    )
    db_session.add(
        CompanySource(
            company_id=company.id,
            source_id=source.id,
            adapter="noop",
            configuration={},
            enabled=True,
        )
    )
    await db_session.commit()

    _REGISTRY["noop"] = NoopAdapter
    try:
        response = await client.post(f"/api/sync/{company.id}")
    finally:
        _REGISTRY.pop("noop", None)

    assert response.status_code == 200
    body = response.json()
    assert body["company"] == "stripe"
    assert len(body["runs"]) == 1
    run = body["runs"][0]
    assert run["status"] == "success"
    assert run["jobs_found"] == 0
    assert run["jobs_new"] == 0

    # A SyncRun row was persisted.
    persisted = (await db_session.execute(select(SyncRun))).scalar_one()
    assert persisted.id == run["sync_run_id"]
    assert persisted.jobs_found == 0
