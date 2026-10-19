"""company_tier + source_type filters, /api/filters/tiers, startup warnings."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.filters import reload_filter_config, warn_unknown_tier_slugs
from app.filters.config import DEFAULT_CONFIG_PATH
from app.models.company_source import CompanySource
from app.models.enums import JobStatus, SourceType
from app.models.job_location import JobLocation
from app.models.job_source import JobSource
from app.repositories.company import CompanyRepo
from app.repositories.job import JobRepo
from app.repositories.source import SourceRepo

# Match the yaml draft so we don't fight it; stripe + spotify are in big_tech.
NO_DEFAULTS = {"role_category": "any", "country": "any", "seniority": "any"}


async def _seed_tier_corpus(db_session: AsyncSession):
    """Seed 4 companies: stripe + spotify in big_tech, ramp + attentive not."""
    # Reload yaml so earlier tests that stubbed the config can't contaminate.
    reload_filter_config(DEFAULT_CONFIG_PATH)

    stripe = await CompanyRepo(db_session).create(name="Stripe", slug="stripe")
    spotify = await CompanyRepo(db_session).create(name="Spotify", slug="spotify")
    ramp = await CompanyRepo(db_session).create(name="Ramp", slug="ramp")
    not_in_tier = await CompanyRepo(db_session).create(
        name="Random Co", slug="random-co"
    )

    official = await SourceRepo(db_session).create(
        name="StripeCareers", type=SourceType.OFFICIAL, provider="stripe-careers"
    )
    ats = await SourceRepo(db_session).create(
        name="Greenhouse", type=SourceType.ATS, provider="greenhouse"
    )
    board = await SourceRepo(db_session).create(
        name="LinkedIn", type=SourceType.BOARD, provider="linkedin"
    )
    await db_session.commit()

    jobs = {}
    for company, src in [
        (stripe, official),
        (spotify, ats),
        (ramp, ats),
        (not_in_tier, board),
    ]:
        job = await JobRepo(db_session).create(
            company_id=company.id,
            canonical_title="Backend Engineer",
            status=JobStatus.ACTIVE,
        )
        db_session.add(
            JobLocation(
                job_id=job.id,
                location_text="San Francisco, CA",
                country="US",
            )
        )
        db_session.add(
            JobSource(
                job_id=job.id,
                source_id=src.id,
                source_job_id=f"{company.slug}-1",
                is_active=True,
            )
        )
        db_session.add(
            CompanySource(
                company_id=company.id,
                source_id=src.id,
                adapter=src.provider,
                enabled=True,
            )
        )
        jobs[company.slug] = job

    await db_session.commit()
    return jobs


async def test_company_tier_filters_to_tier_members_only(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    jobs = await _seed_tier_corpus(db_session)

    response = await client.get(
        "/api/jobs", params={**NO_DEFAULTS, "company_tier": "big_tech"}
    )
    assert response.status_code == 200
    slugs = {_slug_for(j["id"], jobs) for j in response.json()["items"]}
    assert slugs == {"stripe", "spotify"}


async def test_company_tier_intersects_with_explicit_company(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    jobs = await _seed_tier_corpus(db_session)

    # company=stripe,ramp AND company_tier=big_tech → only stripe (ramp isn't in big_tech)
    response = await client.get(
        "/api/jobs",
        params={**NO_DEFAULTS, "company_tier": "big_tech", "company": "stripe,ramp"},
    )
    slugs = {_slug_for(j["id"], jobs) for j in response.json()["items"]}
    assert slugs == {"stripe"}


async def test_source_type_board_only(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    jobs = await _seed_tier_corpus(db_session)

    response = await client.get(
        "/api/jobs", params={**NO_DEFAULTS, "source_type": "board"}
    )
    slugs = {_slug_for(j["id"], jobs) for j in response.json()["items"]}
    assert slugs == {"random-co"}


async def test_source_type_csv_official_plus_ats(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    jobs = await _seed_tier_corpus(db_session)

    response = await client.get(
        "/api/jobs", params={**NO_DEFAULTS, "source_type": "official,ats"}
    )
    slugs = {_slug_for(j["id"], jobs) for j in response.json()["items"]}
    # LinkedIn-only random-co is excluded; the rest keep an official or ATS source.
    assert slugs == {"stripe", "spotify", "ramp"}


async def test_company_tier_and_source_type_compose(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    jobs = await _seed_tier_corpus(db_session)

    # big_tech AND official,ats → stripe + spotify (both have own-portal sources);
    # ramp dropped because it isn't in big_tech.
    response = await client.get(
        "/api/jobs",
        params={**NO_DEFAULTS, "company_tier": "big_tech", "source_type": "official,ats"},
    )
    slugs = {_slug_for(j["id"], jobs) for j in response.json()["items"]}
    assert slugs == {"stripe", "spotify"}


async def test_unknown_company_tier_returns_400(client: AsyncClient) -> None:
    response = await client.get(
        "/api/jobs", params={**NO_DEFAULTS, "company_tier": "nope"}
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "unknown company_tier: nope"}


async def test_invalid_source_type_returns_400(client: AsyncClient) -> None:
    response = await client.get(
        "/api/jobs", params={**NO_DEFAULTS, "source_type": "junk"}
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "invalid source_type: junk"}


async def test_tiers_endpoint_returns_configured_tiers(
    client: AsyncClient,
) -> None:
    reload_filter_config(DEFAULT_CONFIG_PATH)
    response = await client.get("/api/filters/tiers")
    assert response.status_code == 200

    body = response.json()
    keys = {t["key"] for t in body["tiers"]}
    assert "big_tech" in keys
    assert "faang" in keys

    big_tech = next(t for t in body["tiers"] if t["key"] == "big_tech")
    assert big_tech["label"] == "Big Tech"
    assert big_tech["company_count"] > 0


async def test_company_response_includes_tiers(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    reload_filter_config(DEFAULT_CONFIG_PATH)
    stripe = await CompanyRepo(db_session).create(name="Stripe", slug="stripe")
    unlisted = await CompanyRepo(db_session).create(
        name="Random", slug="random-co"
    )
    await db_session.commit()

    stripe_body = (await client.get(f"/api/companies/by-slug/stripe")).json()
    random_body = (await client.get(f"/api/companies/by-slug/random-co")).json()

    assert "big_tech" in stripe_body["tiers"]
    assert random_body["tiers"] == []


async def test_startup_warn_logs_unknown_slugs(
    db_session: AsyncSession, tmp_path, caplog
) -> None:
    # Write a yaml that references two companies, only one of which exists.
    yaml = tmp_path / "filters.yaml"
    yaml.write_text(
        """
company_tiers:
  weird:
    label: Weird
    companies: [known-co, ghost-co]
""".lstrip()
    )
    reload_filter_config(yaml)
    await CompanyRepo(db_session).create(name="Known", slug="known-co")
    await db_session.commit()

    with caplog.at_level("WARNING"):
        unknown = await warn_unknown_tier_slugs(db_session)

    assert unknown == {"weird": ["ghost-co"]}
    assert any("unknown slugs" in record.message for record in caplog.records)

    # Clean up — don't leak the stubbed config into the next test.
    reload_filter_config(DEFAULT_CONFIG_PATH)


def _slug_for(job_id: str, jobs: dict) -> str:
    for slug, job in jobs.items():
        if str(job.id) == job_id:
            return slug
    raise AssertionError(f"unknown job_id {job_id} in test seed")
