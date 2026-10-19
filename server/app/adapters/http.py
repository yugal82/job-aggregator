"""httpx wrapper with per-instance rate limiting, retries, and Retry-After.

Intended usage: one HTTPClient per adapter instance. Adapters share nothing
across companies — a rate-limit budget belongs to the source, not the process.
"""
import asyncio
import logging
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)


RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class HTTPClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        rate_limit_per_second: float = 5.0,
        max_concurrency: int = 5,
        max_retries: int = 3,
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
        self._last_request_time = 0.0
        self._rate_lock = asyncio.Lock()

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
    def _parse_retry_after(response: httpx.Response) -> float | None:
        header = response.headers.get("Retry-After")
        if header is None:
            return None
        try:
            return max(0.0, float(header))
        except ValueError:
            # HTTP-date form not supported for MVP; ignore and fall back to backoff
            return None

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
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

            if response.status_code in RETRYABLE_STATUS and attempt < self._max_retries:
                retry_after = self._parse_retry_after(response)
                wait = retry_after if retry_after is not None else self._backoff_seconds(attempt)
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
