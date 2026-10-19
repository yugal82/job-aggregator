from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.loader import (
    ConfigFile,
    load_config,
    reconcile_companies_from_yaml,
)
from app.models.company import Company
from app.models.company_source import CompanySource
from app.models.enums import SourceType, SyncPriority
from app.models.source import Source
from app.repositories.source import SourceRepo

FIXTURE = Path(__file__).parent / "fixtures/config/companies_test.yaml"


async def _seed_ats_sources(db_session: AsyncSession) -> None:
    """Loader relies on Source rows already existing — mirror seed.py."""
    repo = SourceRepo(db_session)
    await repo.create(name="Greenhouse", type=SourceType.ATS, provider="greenhouse")
    await repo.create(name="Lever", type=SourceType.ATS, provider="lever")
    await repo.create(name="Ashby", type=SourceType.ATS, provider="ashby")
    await db_session.commit()


def test_load_config_parses_and_validates() -> None:
    config = load_config(FIXTURE)
    assert isinstance(config, ConfigFile)
    slugs = [c.slug for c in config.companies]
    assert slugs == ["stripe", "netflix", "no-sources"]
    stripe = config.companies[0]
    assert stripe.sources[0].source_name == "Greenhouse"
    assert stripe.sources[0].priority == SyncPriority.HIGH
    assert config.companies[2].sources == []


async def test_reconcile_inserts_companies_and_links(db_session: AsyncSession) -> None:
    await _seed_ats_sources(db_session)

    stats = await reconcile_companies_from_yaml(db_session, FIXTURE)

    assert stats.companies_created == 3
    assert stats.companies_updated == 0
    assert stats.links_created == 2  # no-sources has no sources
    assert stats.links_updated == 0
    assert stats.unknown_sources == []

    companies = (await db_session.execute(select(func.count()).select_from(Company))).scalar()
    links = (await db_session.execute(select(func.count()).select_from(CompanySource))).scalar()
    assert companies == 3
    assert links == 2


async def test_reconcile_is_idempotent(db_session: AsyncSession) -> None:
    await _seed_ats_sources(db_session)
    await reconcile_companies_from_yaml(db_session, FIXTURE)
    second = await reconcile_companies_from_yaml(db_session, FIXTURE)

    assert second.companies_created == 0
    assert second.companies_updated == 0
    assert second.links_created == 0
    assert second.links_updated == 0


async def test_reconcile_updates_changed_fields(
    db_session: AsyncSession, tmp_path
) -> None:
    await _seed_ats_sources(db_session)
    await reconcile_companies_from_yaml(db_session, FIXTURE)

    edited = tmp_path / "companies.yaml"
    edited.write_text(
        """
companies:
  - slug: stripe
    name: Stripe (Payments)  # ← name changed
    website: https://stripe.com
    careers_url: https://stripe.com/jobs
    sources:
      - source_name: Greenhouse
        adapter: greenhouse
        configuration: { board_token: stripe }
        priority: medium  # ← priority changed from high
""".lstrip()
    )

    stats = await reconcile_companies_from_yaml(db_session, edited)
    assert stats.companies_updated == 1
    assert stats.links_updated == 1
    assert stats.links_created == 0

    stripe = await db_session.scalar(select(Company).where(Company.slug == "stripe"))
    await db_session.refresh(stripe)
    assert stripe.name == "Stripe (Payments)"

    link = await db_session.scalar(
        select(CompanySource).where(CompanySource.company_id == stripe.id)
    )
    await db_session.refresh(link)
    assert link.priority == SyncPriority.MEDIUM


async def test_reconcile_reports_unknown_source_name(
    db_session: AsyncSession, tmp_path
) -> None:
    await _seed_ats_sources(db_session)

    yaml_path = tmp_path / "companies.yaml"
    yaml_path.write_text(
        """
companies:
  - slug: bogus
    name: Bogus Inc
    sources:
      - source_name: NotARealSource
        adapter: whatever
        configuration: {}
""".lstrip()
    )

    stats = await reconcile_companies_from_yaml(db_session, yaml_path)
    assert "NotARealSource" in stats.unknown_sources
    # Company gets created but no link
    link_count = await db_session.scalar(
        select(func.count()).select_from(CompanySource)
    )
    assert link_count == 0


async def test_reconcile_optionally_removes_unlisted_links(
    db_session: AsyncSession, tmp_path
) -> None:
    await _seed_ats_sources(db_session)
    await reconcile_companies_from_yaml(db_session, FIXTURE)

    # New YAML: Stripe now has no Greenhouse link
    yaml_path = tmp_path / "companies.yaml"
    yaml_path.write_text(
        """
companies:
  - slug: stripe
    name: Stripe
    sources: []
""".lstrip()
    )

    stats = await reconcile_companies_from_yaml(
        db_session, yaml_path, remove_unlisted_links=True
    )
    assert stats.links_removed == 1

    stripe = await db_session.scalar(select(Company).where(Company.slug == "stripe"))
    remaining = await db_session.scalar(
        select(func.count())
        .select_from(CompanySource)
        .where(CompanySource.company_id == stripe.id)
    )
    assert remaining == 0


def test_load_config_rejects_extra_fields(tmp_path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
companies:
  - slug: stripe
    name: Stripe
    typo_field: oops
""".lstrip()
    )
    with pytest.raises(Exception):
        load_config(bad)
