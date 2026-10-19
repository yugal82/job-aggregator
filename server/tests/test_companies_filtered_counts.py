"""Contract test for /api/companies filter-aware active_job_count.

Rule the client team enforces (see Phase 15 contract on filtered counts):

    /api/companies?<params>  → company C active_job_count
       ==
    /api/jobs?company=C.slug&<params>  → total

Companies with zero matching rows must still appear (with
active_job_count=0) so the sidebar can toggle them on.
"""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobStatus
from app.models.job_location import JobLocation
from app.repositories.company import CompanyRepo
from app.repositories.job import JobRepo

# Opt out of every default filter — used when we want the raw aggregates.
NO_DEFAULTS = {"role_category": "any", "country": "any", "seniority": "any"}


async def _seed_mixed(db_session: AsyncSession):
    """Seeds three companies with jobs that cross the filter boundaries:

    - Acme (early-career SWE US):     1 matching default
    - Beta (senior non-US):           0 matching default, 2 under any-seniority
    - Zephyr (no jobs at all):        0 everywhere — still must appear in list
    """
    acme = await CompanyRepo(db_session).create(name="Acme", slug="acme")
    beta = await CompanyRepo(db_session).create(name="Beta", slug="beta")
    zephyr = await CompanyRepo(db_session).create(name="Zephyr", slug="zephyr")

    acme_matching = await JobRepo(db_session).create(
        company_id=acme.id,
        canonical_title="Software Engineer I",
        status=JobStatus.ACTIVE,
    )
    db_session.add(
        JobLocation(job_id=acme_matching.id, location_text="San Jose, CA", country="US")
    )

    acme_non_us = await JobRepo(db_session).create(
        company_id=acme.id,
        canonical_title="Software Engineer I",
        status=JobStatus.ACTIVE,
    )
    db_session.add(
        JobLocation(job_id=acme_non_us.id, location_text="London", country="UK")
    )

    for _ in range(2):
        beta_senior = await JobRepo(db_session).create(
            company_id=beta.id,
            canonical_title="Senior Software Engineer",
            status=JobStatus.ACTIVE,
        )
        db_session.add(
            JobLocation(
                job_id=beta_senior.id, location_text="Berlin", country="Germany"
            )
        )

    await db_session.commit()
    return acme, beta, zephyr


def _slug_count_map(payload: dict) -> dict[str, int]:
    return {item["slug"]: item["active_job_count"] for item in payload["items"]}


async def test_default_filter_matches_jobs_endpoint_semantics(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Default `/api/companies` — same quiet filter as `/api/jobs` — the
    per-card count must match `/api/jobs?company=slug` total."""
    await _seed_mixed(db_session)

    companies_resp = await client.get("/api/companies")
    assert companies_resp.status_code == 200
    counts = _slug_count_map(companies_resp.json())

    # Acme has exactly one Software Engineer I in a US location → one match.
    assert counts.get("acme") == 1
    assert counts.get("beta") == 0
    assert counts.get("zephyr") == 0

    # Cross-check: /api/jobs for each slug returns the same total.
    for slug in ("acme", "beta", "zephyr"):
        jobs_resp = await client.get("/api/jobs", params={"company": slug})
        assert jobs_resp.status_code == 200
        assert counts[slug] == jobs_resp.json()["total"], (
            f"{slug}: companies.count={counts[slug]} vs jobs.total={jobs_resp.json()['total']}"
        )


async def test_opt_out_mirrors_unfiltered_counts(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """With every filter disabled, counts should be the full ACTIVE+UPDATED
    totals we had before this contract landed."""
    await _seed_mixed(db_session)

    response = await client.get("/api/companies", params=NO_DEFAULTS)
    counts = _slug_count_map(response.json())

    assert counts.get("acme") == 2    # Both the US + UK Software Engineer I rows
    assert counts.get("beta") == 2    # Both senior Berlin rows
    assert counts.get("zephyr") == 0


async def test_zero_count_companies_still_appear_in_list(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Sidebar needs this: toggling a filter must not hide companies from
    the list, only drop their counts to zero."""
    await _seed_mixed(db_session)

    default_resp = await client.get("/api/companies")
    slugs = {c["slug"] for c in default_resp.json()["items"]}
    # beta and zephyr both have 0 matching under swe+US+entry, but still ship.
    assert {"acme", "beta", "zephyr"}.issubset(slugs)


async def test_seniority_any_flips_counts(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Flip only seniority: beta's senior roles should appear now (same
    country/role filters) while US restriction still masks them."""
    await _seed_mixed(db_session)

    response = await client.get(
        "/api/companies", params={"seniority": "any"}  # keep swe+US defaults
    )
    counts = _slug_count_map(response.json())
    # beta's two senior rows live in Germany → still filtered out by country=US
    assert counts.get("beta") == 0

    response = await client.get(
        "/api/companies",
        params={"seniority": "any", "country": "any"},  # drop US too
    )
    counts = _slug_count_map(response.json())
    assert counts.get("beta") == 2
    # acme still has 2 under seniority=any + country=any (US + UK rows)
    assert counts.get("acme") == 2


async def test_source_type_filter_propagates_to_count(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A `source_type` restriction on `/api/companies` must bind the count
    the same way `/api/jobs?source_type=` does."""
    await _seed_mixed(db_session)

    response = await client.get(
        "/api/companies",
        params={**NO_DEFAULTS, "source_type": "board"},
    )
    counts = _slug_count_map(response.json())
    # No seeded JobSource rows → every count is zero but every company shows.
    assert counts.get("acme") == 0
    assert counts.get("beta") == 0
    assert counts.get("zephyr") == 0


async def test_invalid_source_type_returns_400(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_mixed(db_session)
    response = await client.get("/api/companies", params={"source_type": "junk"})
    assert response.status_code == 400
    assert response.json() == {"detail": "invalid source_type: junk"}


async def test_unknown_company_tier_returns_400(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_mixed(db_session)
    response = await client.get("/api/companies", params={"company_tier": "nope"})
    assert response.status_code == 400
    assert response.json() == {"detail": "unknown company_tier: nope"}


async def test_by_slug_remains_unfiltered(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Contract non-goal: /api/companies/by-slug keeps its unfiltered count.
    Detail page owns its own filtering via /api/jobs."""
    await _seed_mixed(db_session)

    body = (await client.get("/api/companies/by-slug/acme")).json()
    # Both acme rows (US + UK), despite the quiet-default filter semantics.
    assert body["active_job_count"] == 2


async def test_parity_with_jobs_under_each_filter(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Exhaustive-ish parity sweep: a handful of filter combos — the number
    on each company card must equal /api/jobs?company=<slug>&<same>."""
    await _seed_mixed(db_session)

    combos = [
        {},                                                      # all defaults
        NO_DEFAULTS,                                             # all off
        {"seniority": "any"},                                    # keep swe+US
        {"country": "any"},                                      # keep swe+entry
        {"role_category": "any", "seniority": "any"},            # keep US
    ]
    for params in combos:
        companies_resp = await client.get("/api/companies", params=params)
        assert companies_resp.status_code == 200
        counts = _slug_count_map(companies_resp.json())

        for slug, count in counts.items():
            jobs_resp = await client.get(
                "/api/jobs", params={**params, "company": slug}
            )
            assert jobs_resp.status_code == 200, (
                f"/api/jobs failed under {params} for {slug}"
            )
            assert count == jobs_resp.json()["total"], (
                f"params={params} slug={slug}: "
                f"companies.count={count} vs jobs.total={jobs_resp.json()['total']}"
            )
