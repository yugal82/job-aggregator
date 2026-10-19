"""Postgres advisory lock — serializes overlapping sync runs for one
``(company, source)`` pair without needing Redis.

Uses ``pg_try_advisory_lock(bigint)`` on a stable 64-bit key derived from
the lock name. The lock is session-scoped: it is released explicitly via
``pg_advisory_unlock`` AND automatically dropped if the session dies
(crash, container restart, network blip). No TTL to tune.

Why not Redis anymore: single-user deploy has no need for a cross-service
distributed lock. One Postgres instance always exists — reusing it saves
a service and an env var.

Signature mirrors the old ``RedisLock`` so ``job_runner.py`` can swap
implementations with one import change.
"""
import hashlib
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker

from app.db import engine as default_engine

log = logging.getLogger(__name__)


def _advisory_key(key: str) -> int:
    """Fold an arbitrary string key into a signed 64-bit int for
    ``pg_try_advisory_lock``. SHA-256 → first 8 bytes → int, biased into
    signed range so Postgres accepts it."""
    digest = hashlib.sha256(key.encode("utf-8")).digest()[:8]
    value = int.from_bytes(digest, byteorder="big", signed=False)
    # Postgres advisory lock keys are bigint (signed). Map high bit → sign.
    if value >= 2**63:
        value -= 2**64
    return value


class SyncLock:
    """Non-blocking advisory lock. Holds a dedicated AsyncConnection for
    the lifetime of the lock — releasing closes the connection, which
    also releases the lock if ``pg_advisory_unlock`` was skipped (crash)."""

    def __init__(
        self,
        key: str,
        *,
        engine=None,
    ) -> None:
        self.key = key
        self._pg_key = _advisory_key(key)
        self._engine = engine or default_engine
        self._conn: AsyncConnection | None = None
        self._acquired = False

    async def acquire(self) -> bool:
        """Non-blocking: returns False immediately if another holder has it."""
        conn = await self._engine.connect()
        try:
            result = await conn.execute(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": self._pg_key}
            )
            got = bool(result.scalar())
            if not got:
                await conn.close()
                return False
            self._conn = conn
            self._acquired = True
            return True
        except Exception:
            await conn.close()
            raise

    async def release(self) -> None:
        if not self._acquired or self._conn is None:
            return
        try:
            await self._conn.execute(
                text("SELECT pg_advisory_unlock(:k)"), {"k": self._pg_key}
            )
        except Exception:
            log.exception("failed to release advisory lock", extra={"key": self.key})
        finally:
            try:
                await self._conn.close()
            finally:
                self._conn = None
                self._acquired = False

    async def __aenter__(self) -> bool:
        return await self.acquire()

    async def __aexit__(self, *_exc: Any) -> None:
        await self.release()
