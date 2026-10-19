"""Populate baseline ATS sources + reconcile companies from YAML.

Run once against a fresh database:

    python -m app.seed

Idempotent — safe to re-run after every YAML edit.
"""
import asyncio
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.config.loader import reconcile_companies_from_yaml
from app.db import SessionLocal
from app.logging import configure_logging
from app.models.enums import SourceType
from app.models.source import Source
from app.models.user import User
from app.models.user_profile import UserProfile

DEFAULT_USER_ID = 1
DEFAULT_USER_EMAIL = "you@example.com"

# Hard-coded profile for Phase 6 (client). The user can edit this via a
# Phase 7 profile editor; the shape is what the matcher consumes today.
DEFAULT_USER_PROFILE: dict = {
    "target_roles": [
        "backend",
        "fullstack",
        "full stack",
        "full-stack",
        "software engineer",
        "software developer",
        "platform",
        "infrastructure",
        "distributed systems",
    ],
    "target_locations": [
        "Remote",
        "San Francisco",
        "New York",
        "Seattle",
        "Boston",
        "Austin",
        "United States",
    ],
    "skills": [
        "python",
        "typescript",
        "javascript",
        "postgres",
        "react",
        "docker",
        "aws",
    ],
    "years_experience": 1,
    "requires_sponsorship": False,
}

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "companies.yaml"


SOURCES: list[dict[str, Any]] = [
    {
        "name": "Greenhouse",
        "type": SourceType.ATS,
        "provider": "greenhouse",
        "base_url": "https://boards-api.greenhouse.io",
    },
    {
        "name": "Lever",
        "type": SourceType.ATS,
        "provider": "lever",
        "base_url": "https://api.lever.co",
    },
    {
        "name": "Ashby",
        "type": SourceType.ATS,
        "provider": "ashby",
        "base_url": "https://api.ashbyhq.com",
    },
    # OFFICIAL / own-portal sources — rank higher than ATS in canonical URL
    # selection (see app/ingestion/canonical_url.py).
    {
        "name": "AmazonCareers",
        "type": SourceType.OFFICIAL,
        "provider": "amazon-careers",
        "base_url": "https://www.amazon.jobs",
    },
    {
        "name": "NetflixCareers",
        "type": SourceType.OFFICIAL,
        "provider": "netflix-careers",
        "base_url": "https://explore.jobs.netflix.net",
    },
    {
        "name": "MicrosoftCareers",
        "type": SourceType.OFFICIAL,
        "provider": "microsoft-careers",
        # Microsoft jobs come from a user-owned scraper's GitHub mirror; the
        # per-company configuration carries the actual URL (keeps the Source
        # row generic in case we ever point at a different fork).
        "base_url": None,
    },
    {
        "name": "AtlassianCareers",
        "type": SourceType.OFFICIAL,
        "provider": "atlassian-careers",
        "base_url": "https://www.atlassian.com",
    },
    {
        "name": "AppleCareers",
        "type": SourceType.OFFICIAL,
        "provider": "apple-careers",
        "base_url": "https://jobs.apple.com",
    },
    # Generic — each Workday-hosted company puts its host/tenant/site in the
    # company_source.configuration, so this Source row's base_url stays empty.
    {
        "name": "Workday",
        "type": SourceType.OFFICIAL,
        "provider": "workday",
        "base_url": None,
    },
]


async def seed(config_path: Path = DEFAULT_CONFIG_PATH) -> None:
    async with SessionLocal() as session:
        for row in SOURCES:
            exists = await session.scalar(select(Source.id).where(Source.name == row["name"]))
            if exists is None:
                session.add(Source(**row))
                log.info("inserted source", extra={"source_name": row["name"]})

        # Phase 10 single-user mode: all state actions hit this user until
        # Phase 14 adds real auth.
        default_user_exists = await session.scalar(
            select(User.id).where(User.id == DEFAULT_USER_ID)
        )
        if default_user_exists is None:
            session.add(User(id=DEFAULT_USER_ID, email=DEFAULT_USER_EMAIL))
            log.info("inserted default user", extra={"user_id": DEFAULT_USER_ID})

        # Default profile — seeded only if missing so manual edits persist
        # across subsequent `python -m app.seed` runs.
        profile_exists = await session.scalar(
            select(UserProfile.user_id).where(UserProfile.user_id == DEFAULT_USER_ID)
        )
        if profile_exists is None:
            session.add(UserProfile(user_id=DEFAULT_USER_ID, **DEFAULT_USER_PROFILE))
            log.info("inserted default user profile", extra={"user_id": DEFAULT_USER_ID})

        await session.commit()

        stats = await reconcile_companies_from_yaml(session, config_path)
        log.info(
            "reconciled companies from yaml",
            extra={
                "companies_created": stats.companies_created,
                "companies_updated": stats.companies_updated,
                "links_created": stats.links_created,
                "links_updated": stats.links_updated,
                "unknown_sources": stats.unknown_sources,
            },
        )


def main() -> None:
    configure_logging()
    asyncio.run(seed())


if __name__ == "__main__":
    main()
