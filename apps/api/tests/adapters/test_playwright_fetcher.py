"""Tests for PlaywrightFetcher.

We mock the Playwright objects entirely — these tests verify wiring
(robots check, rate-limit, browser lifecycle), not real browser behavior.
A separate slow integration test (out of scope here) would cover real Chromium.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rentwise.adapters.base import RobotsDisallowedError
from rentwise.adapters.playwright_fetcher import PlaywrightFetcher


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

        fetcher = PlaywrightFetcher(user_agent="RentWise/test")
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

        fetcher = PlaywrightFetcher(user_agent="RentWise/test")
        fetcher.robots.is_allowed = AsyncMock(return_value=False)

        with pytest.raises(RobotsDisallowedError):
            await fetcher.fetch_html("https://blocked.test/page")

        fake_pw.chromium.launch.assert_not_called()


async def test_passes_wait_for_selector(fake_pw: MagicMock, fake_page: MagicMock) -> None:
    """wait_for kwarg is forwarded to page.wait_for_selector."""
    with patch("rentwise.adapters.playwright_fetcher.async_playwright") as start_pw:
        start_pw.return_value.start = AsyncMock(return_value=fake_pw)

        fetcher = PlaywrightFetcher(user_agent="RentWise/test")
        fetcher.robots.is_allowed = AsyncMock(return_value=True)

        await fetcher.fetch_html("https://example.test/", wait_for=".listing-card")
        fake_page.wait_for_selector.assert_awaited_once_with(".listing-card", timeout=10000)


async def test_close_is_idempotent(fake_pw: MagicMock) -> None:
    """close() before any fetch is a no-op; close() twice is safe."""
    with patch("rentwise.adapters.playwright_fetcher.async_playwright") as start_pw:
        start_pw.return_value.start = AsyncMock(return_value=fake_pw)

        fetcher = PlaywrightFetcher(user_agent="RentWise/test")

        await fetcher.close()  # never started — no-op
        await fetcher.close()  # double-close — no-op
        fake_pw.stop.assert_not_called()
