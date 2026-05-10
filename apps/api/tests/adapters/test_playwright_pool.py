"""Tests for PlaywrightPool.

The pool is the shared Chromium owner; each unique User-Agent gets its
own ``BrowserContext``. We mock Playwright entirely — these tests verify
the pool's locking, singleton, and shutdown contract, not real browser
behavior.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rentwise.adapters.playwright_pool import PlaywrightPool


@pytest.fixture
def fake_pw() -> MagicMock:
    pw = MagicMock()
    browser = MagicMock()
    browser.close = AsyncMock()
    # Each new_context returns a fresh mock so per-UA contexts are distinct.
    browser.new_context = AsyncMock(side_effect=lambda **_: _make_context())
    pw.chromium.launch = AsyncMock(return_value=browser)
    pw.stop = AsyncMock()
    return pw


def _make_context() -> MagicMock:
    ctx = MagicMock()
    ctx.close = AsyncMock()
    return ctx


def _patch_playwright(fake_pw: MagicMock):
    p = patch("rentwise.adapters.playwright_fetcher.async_playwright")
    return p, fake_pw


async def test_first_get_context_launches_browser(fake_pw: MagicMock) -> None:
    p, _ = _patch_playwright(fake_pw)
    with p as start_pw:
        start_pw.return_value.start = AsyncMock(return_value=fake_pw)

        pool = PlaywrightPool()
        fake_pw.chromium.launch.assert_not_called()
        await pool.get_context("RentWise/A")
        fake_pw.chromium.launch.assert_awaited_once()
        await pool.shutdown()


async def test_same_ua_reuses_context(fake_pw: MagicMock) -> None:
    p, _ = _patch_playwright(fake_pw)
    with p as start_pw:
        start_pw.return_value.start = AsyncMock(return_value=fake_pw)

        pool = PlaywrightPool()
        ctx_a1 = await pool.get_context("RentWise/A")
        ctx_a2 = await pool.get_context("RentWise/A")
        assert ctx_a1 is ctx_a2
        # One launch, one new_context call.
        fake_pw.chromium.launch.assert_awaited_once()
        assert fake_pw.chromium.launch.return_value.new_context.await_count == 1
        await pool.shutdown()


async def test_different_uas_share_browser_separate_contexts(fake_pw: MagicMock) -> None:
    p, _ = _patch_playwright(fake_pw)
    with p as start_pw:
        start_pw.return_value.start = AsyncMock(return_value=fake_pw)

        pool = PlaywrightPool()
        ctx_a = await pool.get_context("RentWise/A")
        ctx_b = await pool.get_context("RentWise/B")
        assert ctx_a is not ctx_b
        # One browser, two contexts.
        fake_pw.chromium.launch.assert_awaited_once()
        assert fake_pw.chromium.launch.return_value.new_context.await_count == 2
        await pool.shutdown()


async def test_concurrent_first_callers_dont_double_launch(fake_pw: MagicMock) -> None:
    """Two coroutines calling get_context concurrently → exactly one launch."""
    p, _ = _patch_playwright(fake_pw)
    with p as start_pw:
        start_pw.return_value.start = AsyncMock(return_value=fake_pw)

        pool = PlaywrightPool()
        await asyncio.gather(
            pool.get_context("RentWise/A"),
            pool.get_context("RentWise/A"),
            pool.get_context("RentWise/B"),
        )
        fake_pw.chromium.launch.assert_awaited_once()
        await pool.shutdown()


async def test_shutdown_closes_contexts_browser_playwright(fake_pw: MagicMock) -> None:
    p, _ = _patch_playwright(fake_pw)
    with p as start_pw:
        start_pw.return_value.start = AsyncMock(return_value=fake_pw)

        pool = PlaywrightPool()
        ctx = await pool.get_context("RentWise/A")
        await pool.shutdown()

        ctx.close.assert_awaited_once()
        fake_pw.chromium.launch.return_value.close.assert_awaited_once()
        fake_pw.stop.assert_awaited_once()


async def test_shutdown_is_idempotent(fake_pw: MagicMock) -> None:
    """Second shutdown is a no-op; doesn't raise or double-close."""
    p, _ = _patch_playwright(fake_pw)
    with p as start_pw:
        start_pw.return_value.start = AsyncMock(return_value=fake_pw)

        pool = PlaywrightPool()
        await pool.get_context("RentWise/A")
        await pool.shutdown()
        await pool.shutdown()  # no-op
        fake_pw.stop.assert_awaited_once()


async def test_shared_singleton_returns_same_instance() -> None:
    """`shared()` returns the same instance across calls until reset."""
    a = await PlaywrightPool.shared()
    b = await PlaywrightPool.shared()
    assert a is b
    await PlaywrightPool.reset()
    c = await PlaywrightPool.shared()
    assert c is not a
    await PlaywrightPool.reset()


async def test_reset_tears_down_singleton(fake_pw: MagicMock) -> None:
    p, _ = _patch_playwright(fake_pw)
    with p as start_pw:
        start_pw.return_value.start = AsyncMock(return_value=fake_pw)

        pool = await PlaywrightPool.shared()
        await pool.get_context("RentWise/A")
        await PlaywrightPool.reset()
        fake_pw.stop.assert_awaited_once()
