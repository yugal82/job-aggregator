import time

import httpx

from app.adapters.http import HTTPClient


async def test_retries_on_500_then_succeeds() -> None:
    calls: list[int] = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        calls[0] += 1
        if calls[0] < 3:
            return httpx.Response(500)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = HTTPClient(
        base_url="https://mock",
        transport=transport,
        max_retries=3,
        rate_limit_per_second=0,  # disable throttle for speed
    )
    try:
        response = await client.get("/foo")
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert calls[0] == 3
    finally:
        await client.close()


async def test_gives_up_after_max_retries() -> None:
    calls: list[int] = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        calls[0] += 1
        return httpx.Response(503)

    client = HTTPClient(
        base_url="https://mock",
        transport=httpx.MockTransport(handler),
        max_retries=2,
        rate_limit_per_second=0,
    )
    try:
        response = await client.get("/foo")
        assert response.status_code == 503
        assert calls[0] == 3  # initial + 2 retries
    finally:
        await client.close()


async def test_honors_retry_after_seconds() -> None:
    timestamps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        timestamps.append(time.monotonic())
        if len(timestamps) == 1:
            return httpx.Response(429, headers={"Retry-After": "0.3"})
        return httpx.Response(200)

    client = HTTPClient(
        base_url="https://mock",
        transport=httpx.MockTransport(handler),
        max_retries=3,
        rate_limit_per_second=0,
    )
    try:
        response = await client.get("/foo")
        assert response.status_code == 200
        assert timestamps[1] - timestamps[0] >= 0.28  # allow small scheduler slop
    finally:
        await client.close()


async def test_rate_limit_enforces_min_interval() -> None:
    timestamps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        timestamps.append(time.monotonic())
        return httpx.Response(200)

    client = HTTPClient(
        base_url="https://mock",
        transport=httpx.MockTransport(handler),
        max_retries=0,
        rate_limit_per_second=5.0,  # 200ms min interval
    )
    try:
        for _ in range(3):
            await client.get("/foo")
        gaps = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
        assert all(g >= 0.18 for g in gaps), gaps
    finally:
        await client.close()


async def test_rate_limited_gets_a_longer_retry_budget(monkeypatch) -> None:
    """A 429 without Retry-After backs off 5s, 10s, ... and is retried past
    `max_retries` — Workday throttles CI runners for minutes, not seconds."""
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("app.adapters.http.asyncio.sleep", fake_sleep)
    calls = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        calls[0] += 1
        return httpx.Response(429) if calls[0] <= 5 else httpx.Response(200)

    client = HTTPClient(
        base_url="https://mock",
        transport=httpx.MockTransport(handler),
        max_retries=3,
        max_rate_limit_retries=5,
        rate_limit_per_second=0,
    )
    try:
        response = await client.get("/foo")
        assert response.status_code == 200
        assert calls[0] == 6
        assert sleeps == [5.0, 10.0, 20.0, 40.0, 60.0]
    finally:
        await client.close()


async def test_non_rate_limit_errors_keep_the_short_budget(monkeypatch) -> None:
    async def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr("app.adapters.http.asyncio.sleep", fake_sleep)
    calls = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        calls[0] += 1
        return httpx.Response(503)

    client = HTTPClient(
        base_url="https://mock",
        transport=httpx.MockTransport(handler),
        max_retries=2,
        max_rate_limit_retries=5,
        rate_limit_per_second=0,
    )
    try:
        assert (await client.get("/foo")).status_code == 503
        assert calls[0] == 3
    finally:
        await client.close()


def test_retry_after_parses_http_date_and_caps() -> None:
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime

    from app.adapters.http import MAX_RETRY_AFTER_SECONDS

    soon = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=30), usegmt=True)
    parsed = HTTPClient._parse_retry_after(httpx.Response(429, headers={"Retry-After": soon}))
    assert parsed is not None and 25 <= parsed <= 30

    huge = httpx.Response(429, headers={"Retry-After": "3600"})
    assert HTTPClient._parse_retry_after(huge) == MAX_RETRY_AFTER_SECONDS

    junk = httpx.Response(429, headers={"Retry-After": "soon-ish"})
    assert HTTPClient._parse_retry_after(junk) is None


async def test_for_source_reads_rate_limit_from_config() -> None:
    default = HTTPClient.for_source("https://mock", {})
    paced = HTTPClient.for_source("https://mock", {"rate_limit_per_second": 0.5})
    try:
        assert default._min_interval == 0.2
        assert paced._min_interval == 2.0
    finally:
        await default.close()
        await paced.close()
