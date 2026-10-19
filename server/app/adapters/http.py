"""httpx wrapper with per-instance rate limiting, retries, and Retry-After.

Intended usage: one HTTPClient per adapter instance. Adapters share nothing
across companies — a rate-limit budget belongs to the source, not the process.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

log = logging.getLogger(__name__)


RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}

# Never sleep longer than this on a server-supplied Retry-After.
MAX_RETRY_AFTER_SECONDS = 120.0


class HTTPClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        rate_limit_per_second: float = 5.0,
        max_concurrency: int = 5,
        max_retries: int = 3,
        max_rate_limit_retries: int = 5,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url or "",
            timeout=timeout_seconds,
            transport=transport,
            headers=headers or {},
        )
        self._sem = asyncio.Semaphore(max_concurrency)
        self._min_interval = 1.0 / rate_limit_per_second if rate_limit_per_second > 0 else 0.0
        self._max_retries = max_retries
        # 429s get their own, longer budget: career sites (Workday especially)
        # throttle shared CI runner IPs and need minutes, not seconds, to cool.
        self._max_rate_limit_retries = max(max_retries, max_rate_limit_retries)
        self._last_request_time = 0.0
        self._rate_lock = asyncio.Lock()

    @classmethod
    def for_source(cls, base_url: str | None, config: dict[str, Any] | None) -> "HTTPClient":
        """Client for one company source. ``rate_limit_per_second`` in the
        source's yaml ``configuration`` overrides the default pacing for
        tenants that throttle hard (e.g. Salesforce's Workday)."""
        rate = (config or {}).get("rate_limit_per_second")
        if rate is None:
            return cls(base_url=base_url or "")
        return cls(base_url=base_url or "", rate_limit_per_second=float(rate))

    async def _throttle(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._rate_lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_request_time)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_time = time.monotonic()

    @staticmethod
    def _backoff_seconds(attempt: int) -> float:
        # 0.5, 1, 2, 4, ... capped at 30s
        return min(0.5 * (2**attempt), 30.0)

    @staticmethod
    def _rate_limit_backoff_seconds(attempt: int) -> float:
        # 5, 10, 20, 40, 60, ... capped at 60s
        return min(5.0 * (2**attempt), 60.0)

    @staticmethod
    def _parse_retry_after(response: httpx.Response) -> float | None:
        header = response.headers.get("Retry-After")
        if header is None:
            return None
        try:
            seconds = float(header)
        except ValueError:
            try:
                when = parsedate_to_datetime(header)
            except (TypeError, ValueError):
                return None
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            seconds = (when - datetime.now(timezone.utc)).total_seconds()
        return min(max(0.0, seconds), MAX_RETRY_AFTER_SECONDS)

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self._max_rate_limit_retries + 1):
            async with self._sem:
                await self._throttle()
                try:
                    response = await self._client.request(method, url, **kwargs)
                except httpx.TransportError as exc:
                    last_error = exc
                    if attempt >= self._max_retries:
                        raise
                    wait = self._backoff_seconds(attempt)
                    log.warning(
                        "http transport error, retrying",
                        extra={"url": url, "attempt": attempt, "wait": wait, "error": str(exc)},
                    )
                    await asyncio.sleep(wait)
                    continue

            rate_limited = response.status_code == 429
            budget = self._max_rate_limit_retries if rate_limited else self._max_retries
            if response.status_code in RETRYABLE_STATUS and attempt < budget:
                retry_after = self._parse_retry_after(response)
                if retry_after is not None:
                    wait = retry_after
                elif rate_limited:
                    wait = self._rate_limit_backoff_seconds(attempt)
                else:
                    wait = self._backoff_seconds(attempt)
                log.warning(
                    "http retryable status, retrying",
                    extra={
                        "url": url,
                        "status": response.status_code,
                        "attempt": attempt,
                        "wait": wait,
                    },
                )
                await asyncio.sleep(wait)
                continue

            return response

        # Unreachable in practice: either we returned a response or re-raised.
        assert last_error is not None
        raise last_error

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "HTTPClient":
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.close()
