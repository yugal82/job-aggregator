from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings

_settings = get_settings()

# Runtime engine uses ``database_url`` — this is the pooled URL on Neon and
# the only URL on local docker-compose. Alembic migrations use the direct
# URL instead (``settings.migration_database_url``) — see ``migrations/env.py``.
engine = create_async_engine(
    _settings.runtime_database_url, pool_pre_ping=True, future=True
)

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """FastAPI dependency exposing the sessionmaker itself.

    Endpoints that need to spawn background work with their own transaction
    boundaries take this instead of a single session — that lets tests swap in
    a test-database factory without patching module state.
    """
    return SessionLocal
