"""Browser fetcher: composes RobotsCache + RateLimitedFetcher + Chromium.

One instance per adapter — keeps a single browser process alive for the
adapter's lifetime, opens a fresh page per request, closes it after.
Subclasses of SourceAdapter compose this and call `fetch_html`.
"""

from __future__ import annotations

import structlog
from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from rentwise.adapters.base import RobotsDisallowedError
from rentwise.adapters.ratelimit import RateLimitedFetcher
from rentwise.adapters.robots import RobotsCache

log = structlog.get_logger(__name__)


class PlaywrightFetcher:
    """Composable browser fetcher with robots + rate-limit integration."""

    def __init__(
        self,
        *,
        user_agent: str,
        rate_per_sec: float = 1.0,
        jitter_ms: tuple[int, int] = (500, 1500),
        page_timeout_ms: int = 30_000,
        selector_timeout_ms: int = 10_000,
    ) -> None:
        self.user_agent = user_agent
        self.page_timeout_ms = page_timeout_ms
        self.selector_timeout_ms = selector_timeout_ms
        self.robots = RobotsCache(user_agent=user_agent)
        self.fetcher = RateLimitedFetcher(rate_per_sec=rate_per_sec, jitter_ms=jitter_ms)
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def _ensure_browser(self) -> BrowserContext:
        if self._context is not None:
            return self._context
        try:
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=True)
            self._context = await self._browser.new_context(user_agent=self.user_agent)
        except BaseException:
            if self._browser is not None:
                try:
                    await self._browser.close()
                except BaseException:
                    pass
                self._browser = None
            if self._pw is not None:
                try:
                    await self._pw.stop()
                except BaseException:
                    pass
                self._pw = None
            self._context = None
            raise
        log.info("playwright.browser.started", user_agent=self.user_agent)
        return self._context

    async def fetch_html(self, url: str, *, wait_for: str | None = None) -> str:
        """Fetch rendered HTML, respecting robots + rate limits.

        Raises RobotsDisallowedError if robots.txt forbids the URL.
        """
        if not await self.robots.is_allowed(url):
            raise RobotsDisallowedError(f"robots.txt disallows {url}")
        async with self.fetcher:
            ctx = await self._ensure_browser()
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=self.page_timeout_ms)
                if wait_for:
                    await page.wait_for_selector(wait_for, timeout=self.selector_timeout_ms)
                return await page.content()
            finally:
                await page.close()

    async def close(self) -> None:
        """Idempotent shutdown."""
        browser, pw = self._browser, self._pw
        self._browser = None
        self._pw = None
        self._context = None
        try:
            if browser is not None:
                await browser.close()
        finally:
            if pw is not None:
                await pw.stop()
