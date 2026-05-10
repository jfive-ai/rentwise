"""Tests for PlaywrightFetcher.

We mock the Playwright objects entirely — these tests verify wiring
(robots check, rate-limit, page lifecycle), not real browser behavior.
A separate slow integration test (out of scope here) would cover real
Chromium. Browser-process lifecycle is owned by ``PlaywrightPool`` —
see ``test_playwright_pool.py`` for those assertions.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rentwise.adapters.base import RobotsDisallowedError
from rentwise.adapters.playwright_fetcher import PlaywrightFetcher
from rentwise.adapters.playwright_pool import PlaywrightPool


@pytest.fixture
def fake_page() -> MagicMock:
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.content = AsyncMock(return_value="<html>ok</html>")
    page.close = AsyncMock()
    return page


@pytest.fixture
def fake_context(fake_page: MagicMock) -> MagicMock:
    ctx = MagicMock()
    ctx.new_page = AsyncMock(return_value=fake_page)
    ctx.close = AsyncMock()
    return ctx


@pytest.fixture
def fake_browser(fake_context: MagicMock) -> MagicMock:
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=fake_context)
    browser.close = AsyncMock()
    return browser


@pytest.fixture
def fake_pw(fake_browser: MagicMock) -> MagicMock:
    pw = MagicMock()
    pw.chromium.launch = AsyncMock(return_value=fake_browser)
    pw.stop = AsyncMock()
    return pw


async def test_lazy_browser_start(fake_pw: MagicMock, fake_page: MagicMock) -> None:
    """The browser is not launched until the first fetch."""
    with patch("rentwise.adapters.playwright_fetcher.async_playwright") as start_pw:
        start_pw.return_value.start = AsyncMock(return_value=fake_pw)

        # Use an injected pool so we control its lifetime in this test.
        pool = PlaywrightPool()
        fetcher = PlaywrightFetcher(user_agent="RentWise/test", pool=pool)
        # Override robots to always allow
        fetcher.robots.is_allowed = AsyncMock(return_value=True)

        # Browser not yet launched
        fake_pw.chromium.launch.assert_not_called()

        html = await fetcher.fetch_html("https://example.test/page")
        assert html == "<html>ok</html>"
        fake_pw.chromium.launch.assert_awaited_once()

        # Second call reuses the same browser
        await fetcher.fetch_html("https://example.test/other")
        fake_pw.chromium.launch.assert_awaited_once()

        await fetcher.close()
        fake_pw.stop.assert_awaited_once()


async def test_robots_disallowed_raises(fake_pw: MagicMock) -> None:
    """RobotsDisallowedError when robots forbids the URL — browser never opens."""
    with patch("rentwise.adapters.playwright_fetcher.async_playwright") as start_pw:
        start_pw.return_value.start = AsyncMock(return_value=fake_pw)

        pool = PlaywrightPool()
        fetcher = PlaywrightFetcher(user_agent="RentWise/test", pool=pool)
        fetcher.robots.is_allowed = AsyncMock(return_value=False)

        with pytest.raises(RobotsDisallowedError):
            await fetcher.fetch_html("https://blocked.test/page")

        fake_pw.chromium.launch.assert_not_called()
        await fetcher.close()


async def test_passes_wait_for_selector(fake_pw: MagicMock, fake_page: MagicMock) -> None:
    """wait_for kwarg is forwarded to page.wait_for_selector."""
    with patch("rentwise.adapters.playwright_fetcher.async_playwright") as start_pw:
        start_pw.return_value.start = AsyncMock(return_value=fake_pw)

        pool = PlaywrightPool()
        fetcher = PlaywrightFetcher(user_agent="RentWise/test", pool=pool)
        fetcher.robots.is_allowed = AsyncMock(return_value=True)

        await fetcher.fetch_html("https://example.test/", wait_for=".listing-card")
        fake_page.wait_for_selector.assert_awaited_once_with(".listing-card", timeout=10000)
        await fetcher.close()


async def test_close_is_idempotent(fake_pw: MagicMock) -> None:
    """close() before any fetch is a no-op; close() twice is safe."""
    with patch("rentwise.adapters.playwright_fetcher.async_playwright") as start_pw:
        start_pw.return_value.start = AsyncMock(return_value=fake_pw)

        pool = PlaywrightPool()
        fetcher = PlaywrightFetcher(user_agent="RentWise/test", pool=pool)

        await fetcher.close()  # never started — no-op
        await fetcher.close()  # double-close — no-op
        fake_pw.stop.assert_not_called()


async def test_page_closed_when_goto_raises(fake_pw: MagicMock, fake_page: MagicMock) -> None:
    """If page.goto raises, the page is still closed (resource cleanup)."""
    with patch("rentwise.adapters.playwright_fetcher.async_playwright") as start_pw:
        start_pw.return_value.start = AsyncMock(return_value=fake_pw)
        fake_page.goto = AsyncMock(side_effect=TimeoutError("nav timeout"))

        pool = PlaywrightPool()
        fetcher = PlaywrightFetcher(user_agent="RentWise/test", pool=pool)
        fetcher.robots.is_allowed = AsyncMock(return_value=True)

        with pytest.raises(TimeoutError):
            await fetcher.fetch_html("https://slow.test/")

        fake_page.close.assert_awaited_once()
        await fetcher.close()
