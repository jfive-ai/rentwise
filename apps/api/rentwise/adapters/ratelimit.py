"""Per-source rate limiter: semaphore + min-interval + jitter."""

from __future__ import annotations

import asyncio
import random
from typing import Protocol


class _Clock(Protocol):
    def time(self) -> float: ...

    async def sleep(self, secs: float) -> None: ...


class _RealClock:
    def time(self) -> float:
        import time

        return time.monotonic()

    async def sleep(self, secs: float) -> None:
        await asyncio.sleep(secs)


class RateLimitedFetcher:
    """Single-flight + min-interval + jitter, per instance.

    One instance per source — guarantees no parallel requests against the same
    origin even if the aggregator fans out concurrently.
    """

    def __init__(
        self,
        rate_per_sec: float,
        clock: _Clock | None = None,
        jitter_ms: tuple[int, int] = (500, 1500),
    ) -> None:
        if rate_per_sec <= 0:
            raise ValueError("rate_per_sec must be positive")
        self.min_interval = 1.0 / rate_per_sec
        self.jitter_ms = jitter_ms
        self.clock = clock or _RealClock()
        self._semaphore = asyncio.Semaphore(1)
        self._last_request_at: float | None = None

    async def __aenter__(self) -> RateLimitedFetcher:
        await self._semaphore.acquire()
        try:
            jitter_lo, jitter_hi = self.jitter_ms
            jitter = random.uniform(jitter_lo / 1000, jitter_hi / 1000)
            await self.clock.sleep(jitter)

            if self._last_request_at is not None:
                elapsed = self.clock.time() - self._last_request_at
                wait = self.min_interval - elapsed
                if wait > 0:
                    await self.clock.sleep(wait)

            self._last_request_at = self.clock.time()
        except BaseException:
            self._semaphore.release()
            raise
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._semaphore.release()
