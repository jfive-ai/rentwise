"""Process-wide Playwright pool: one Chromium, per-UA contexts.

Before this module, every adapter that used :class:`PlaywrightFetcher`
launched its own Chromium. With 5 enabled adapters that's 5x 150 MB +
5x 1-2 s warmup per /search. The pool collapses those into one launch
per process, sharing the browser across adapters but giving each
distinct User-Agent its own ``BrowserContext`` so cookies and identity
stay separate per source.

The pool is acquired via :meth:`PlaywrightPool.shared` (a singleton)
under a lock — concurrent first-callers won't race-leak browsers. For
tests, :meth:`PlaywrightPool.reset` tears down the singleton; tests can
also construct an isolated :class:`PlaywrightPool()` and inject it into
:class:`PlaywrightFetcher`.

We deliberately import ``async_playwright`` indirectly through
``rentwise.adapters.playwright_fetcher`` so existing tests that patch
``rentwise.adapters.playwright_fetcher.async_playwright`` keep working
once the fetcher delegates here.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, ClassVar

import structlog

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Playwright

log = structlog.get_logger(__name__)


class PlaywrightPool:
    """Shared Chromium + per-UA ``BrowserContext`` cache.

    Lifecycle:
        - First call to :meth:`get_context` lazy-launches Chromium.
        - Subsequent calls reuse the same browser; each unique
          ``user_agent`` gets its own context.
        - :meth:`shutdown` closes contexts → browser → playwright.
    """

    _instance: ClassVar[PlaywrightPool | None] = None
    _instance_lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    def __init__(self) -> None:
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._contexts: dict[str, BrowserContext] = {}
        # Single lock guards launch + context-create + shutdown so the
        # "two concurrent acquires" race can't double-launch.
        self._lock = asyncio.Lock()

    @classmethod
    async def shared(cls) -> PlaywrightPool:
        """Return the process-wide singleton, lazy-creating it if needed."""
        if cls._instance is None:
            async with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    async def reset(cls) -> None:
        """Tear down the singleton; the next ``shared()`` call starts fresh.

        Tests use this between cases so state from one test (mock
        contexts, fake browsers) doesn't leak into the next.
        """
        async with cls._instance_lock:
            inst = cls._instance
            cls._instance = None
        if inst is not None:
            await inst.shutdown()

    async def get_context(self, user_agent: str) -> BrowserContext:
        """Return the (lazy-created) context for ``user_agent``.

        Lazy-launches Chromium on first use. Holding ``_lock`` for the
        full launch+context-create makes this safe under concurrent
        callers — the second caller waits on the lock and then sees
        ``self._browser`` already set.
        """
        async with self._lock:
            if self._browser is None:
                # Indirect lookup keeps the module patchable from tests
                # that monkey-patch `playwright_fetcher.async_playwright`.
                from rentwise.adapters import playwright_fetcher as _pf

                self._pw = await _pf.async_playwright().start()
                self._browser = await self._pw.chromium.launch(headless=True)
                log.info("playwright_pool.browser.started")
            ctx = self._contexts.get(user_agent)
            if ctx is None:
                ctx = await self._browser.new_context(user_agent=user_agent)
                self._contexts[user_agent] = ctx
                log.info(
                    "playwright_pool.context.created",
                    user_agent=user_agent,
                    contexts_open=len(self._contexts),
                )
            return ctx

    async def shutdown(self) -> None:
        """Close every context, then the browser, then stop playwright.

        Idempotent: a second call after teardown is a no-op. Best-effort
        on each step — a stuck close should not prevent later steps from
        running, since this typically runs at process exit.
        """
        async with self._lock:
            contexts = list(self._contexts.values())
            self._contexts.clear()
            browser, pw = self._browser, self._pw
            self._browser = None
            self._pw = None

        for ctx in contexts:
            try:
                await ctx.close()
            except Exception as exc:
                log.info("playwright_pool.context.close_failed", error=str(exc))
        if browser is not None:
            try:
                await browser.close()
            except Exception as exc:
                log.info("playwright_pool.browser.close_failed", error=str(exc))
        if pw is not None:
            try:
                await pw.stop()
            except Exception as exc:
                log.info("playwright_pool.stop_failed", error=str(exc))
