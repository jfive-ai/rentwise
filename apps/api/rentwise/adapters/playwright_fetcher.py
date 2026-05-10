"""Browser fetcher: composes RobotsCache + RateLimitedFetcher + a shared Playwright pool.

Adapters call :meth:`fetch_html`. The browser process is managed by
:class:`PlaywrightPool`, which is shared across the whole API process —
one Chromium, per-UA contexts. Before the pool, each adapter launched
its own Chromium (5 enabled adapters → 5 launches per /search).

Backwards-compat: ``async_playwright`` is still imported here so tests
that ``patch("rentwise.adapters.playwright_fetcher.async_playwright")``
continue to work — the pool resolves ``async_playwright`` indirectly
through this module.

Tests can pass ``pool=PlaywrightPool()`` for an isolated pool whose
lifetime they own (``await fetcher.close()`` shuts that pool down).
"""

from __future__ import annotations

import structlog
from playwright.async_api import async_playwright

from rentwise.adapters.base import RobotsDisallowedError
from rentwise.adapters.playwright_pool import PlaywrightPool
from rentwise.adapters.ratelimit import RateLimitedFetcher
from rentwise.adapters.robots import RobotsCache

log = structlog.get_logger(__name__)

# Re-exported so legacy callers / tests keep their import paths working.
__all__ = ["PlaywrightFetcher", "async_playwright"]


class PlaywrightFetcher:
    """Robots + rate-limit + per-page wrapper around a shared Playwright pool."""

    def __init__(
        self,
        *,
        user_agent: str,
        rate_per_sec: float = 1.0,
        jitter_ms: tuple[int, int] = (500, 1500),
        page_timeout_ms: int = 30_000,
        selector_timeout_ms: int = 10_000,
        pool: PlaywrightPool | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.page_timeout_ms = page_timeout_ms
        self.selector_timeout_ms = selector_timeout_ms
        self.robots = RobotsCache(user_agent=user_agent)
        self.fetcher = RateLimitedFetcher(rate_per_sec=rate_per_sec, jitter_ms=jitter_ms)
        # When `pool` is None we use the process-wide singleton. When a
        # pool is passed in (test isolation, custom lifetimes), we own
        # its shutdown — `close()` tears it down. Production code never
        # passes a pool; the app shutdown hook closes the singleton.
        self._injected_pool = pool

    async def _resolve_pool(self) -> PlaywrightPool:
        if self._injected_pool is not None:
            return self._injected_pool
        return await PlaywrightPool.shared()

    async def fetch_html(self, url: str, *, wait_for: str | None = None) -> str:
        """Fetch rendered HTML, respecting robots + rate limits.

        Raises :class:`RobotsDisallowedError` if robots.txt forbids the URL.
        """
        if not await self.robots.is_allowed(url):
            raise RobotsDisallowedError(f"robots.txt disallows {url}")
        async with self.fetcher:
            pool = await self._resolve_pool()
            ctx = await pool.get_context(self.user_agent)
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=self.page_timeout_ms)
                if wait_for:
                    await page.wait_for_selector(wait_for, timeout=self.selector_timeout_ms)
                return await page.content()
            finally:
                await page.close()

    async def close(self) -> None:
        """Idempotent shutdown.

        For the default (shared) pool this is a no-op — the pool is owned
        by the application lifecycle. For an injected pool we shut it
        down so test callers don't leak browsers.
        """
        if self._injected_pool is not None:
            await self._injected_pool.shutdown()
