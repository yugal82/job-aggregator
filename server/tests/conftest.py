from collections.abc import AsyncIterator

import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings
from app.db import get_session, get_session_factory
from app.main import app
from app.models import Base


ENUM_TYPES = (
    "source_type",
    "job_status",
    "sync_priority",
    "sync_run_status",
)


async def _ensure_database_exists(url: str) -> None:
    """Create the test database if it doesn't exist (CREATE DATABASE needs AUTOCOMMIT)."""
    url_obj = make_url(url)
    db_name = url_obj.database
    if not db_name:
        return

    admin_url = url_obj.set(database="postgres")
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as conn:
            exists = await conn.scalar(
                sa.text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name}
            )
            if not exists:
                await conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    finally:
        await admin_engine.dispose()


async def _reset_schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        for enum in ENUM_TYPES:
            await conn.execute(sa.text(f"DROP TYPE IF EXISTS {enum}"))
        await conn.run_sync(Base.metadata.create_all)


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    settings = get_settings()
    url = settings.test_database_url or settings.database_url

    await _ensure_database_exists(url)

    engine = create_async_engine(url, pool_pre_ping=True, future=True)

    await _reset_schema(engine)
    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        for enum in ENUM_TYPES:
            await conn.execute(sa.text(f"DROP TYPE IF EXISTS {enum}"))
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(test_engine) -> async_sessionmaker[AsyncSession]:
    """Sessionmaker bound to the test engine — pass into run_sync in tests."""
    return async_sessionmaker(test_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(test_engine, session_factory) -> AsyncIterator[AsyncSession]:
    """Fresh session per test; wipes table data (not schema) so tests are isolated."""
    async with test_engine.begin() as conn:
        table_names = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
        await conn.execute(sa.text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))

    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    def _override_factory() -> async_sessionmaker[AsyncSession]:
        return session_factory

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_session_factory] = _override_factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
