"""Postgres advisory lock tests.

The lock is session-scoped — holding one connection per lock, released
explicitly or when the connection drops. Non-blocking: ``acquire()``
returns False immediately when another holder has it.
"""
import uuid

from app.services.sync_lock import SyncLock, _advisory_key


def _unique_key() -> str:
    return f"test:lock:{uuid.uuid4().hex}"


async def test_acquire_release_cycle() -> None:
    key = _unique_key()
    async with SyncLock(key) as acquired:
        assert acquired is True


async def test_second_holder_is_blocked_until_release() -> None:
    key = _unique_key()

    first = SyncLock(key)
    second = SyncLock(key)

    assert await first.acquire() is True
    try:
        assert await second.acquire() is False
    finally:
        await first.release()

    # Once released, the second waiter can now grab it.
    assert await second.acquire() is True
    await second.release()


async def test_release_is_idempotent_when_not_held() -> None:
    """Calling release() without having acquired must not blow up — this
    happens in the worker when adapter.discover() throws before acquire
    returned true."""
    lock = SyncLock(_unique_key())
    await lock.release()  # no acquire first


async def test_advisory_key_is_deterministic_and_in_bigint_range() -> None:
    key = "sync:nvidia:workday"
    first = _advisory_key(key)
    second = _advisory_key(key)
    assert first == second
    # Postgres bigint range: -2^63 .. 2^63 - 1
    assert -(2**63) <= first < 2**63


async def test_different_keys_do_not_collide() -> None:
    """Two different sync targets must get different lock keys so
    unrelated syncs run concurrently."""
    key_a = _unique_key()
    key_b = _unique_key()

    a = SyncLock(key_a)
    b = SyncLock(key_b)

    assert await a.acquire() is True
    try:
        assert await b.acquire() is True
        await b.release()
    finally:
        await a.release()
