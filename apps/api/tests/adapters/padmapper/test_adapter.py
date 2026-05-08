"""Tests for the PadMapper scaffold adapter (Phase 8 PR-D).

Hard rules these tests enforce:
- Disallowed paths (/api, /backlinks, /external, /static, *cost-calculator)
  and any URL with `box=` query parameter cause health_check → "blocked".
- The adapter is NOT registered in `_build_adapters` when
  RENTWISE_PADMAPPER_ENABLED=false (the default).
- When enabled with a synthetic fixture, search() returns the empty list
  the scaffold's _extract stub produces — and never live-fetches.
- Description snippets stay ≤200 chars per operational-rules.md.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest

from rentwise.adapters.base import RobotsDisallowedError
from rentwise.adapters.padmapper.adapter import (
    PadMapperAdapter,
    is_url_allowed,
)
from rentwise.adapters.playwright_fetcher import PlaywrightFetcher
from rentwise.models import NormalizedQuery, RawListing

FIX = Path(__file__).resolve().parent / "fixtures"


class _StubRobots:
    """Minimal RobotsCache stand-in for tests; configurable allow/deny."""

    def __init__(self, allow: bool = True) -> None:
        self.allow = allow

    async def is_allowed(self, url: str) -> bool:
        _ = url
        return self.allow


class _StubFetcher:
    """In-process stand-in for PlaywrightFetcher — never launches a browser."""

    def __init__(self, html: str = "", *, robots_allow: bool = True) -> None:
        self.html = html
        self.robots = _StubRobots(allow=robots_allow)
        self.fetched_urls: list[str] = []
        self.closed = False

    async def fetch_html(self, url: str, *, wait_for: str | None = None) -> str:
        _ = wait_for
        if not await self.robots.is_allowed(url):
            raise RobotsDisallowedError(f"robots.txt disallows {url}")
        self.fetched_urls.append(url)
        return self.html

    async def close(self) -> None:
        self.closed = True


def _make_adapter(
    *,
    html: str = "",
    robots_allow: bool = True,
) -> tuple[PadMapperAdapter, _StubFetcher]:
    fetcher = _StubFetcher(html=html, robots_allow=robots_allow)
    # Cast through Any: _StubFetcher implements the same surface but isn't a
    # subclass of PlaywrightFetcher (no shared base type by design).
    adapter = PadMapperAdapter(
        user_agent="RentWise-test/0.1",
        jitter_ms=(0, 0),
        fetcher=cast(PlaywrightFetcher, fetcher),
    )
    return adapter, fetcher


# ---------------------------------------------------------------------------
# is_url_allowed — robots.txt-disallowed paths and `box=` query param
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://padmapper.com/api/listings",
        "https://padmapper.com/api",
        "https://padmapper.com/backlinks/abc",
        "https://padmapper.com/external/foo",
        "https://padmapper.com/static/main.js",
        "https://padmapper.com/buildings/some-id/cost-calculator",
        "https://padmapper.com/rentals/some-id/cost-calculator",
        "https://padmapper.com/apartments/vancouver-bc?box=1,2,3,4",
        "https://padmapper.com/apartments/vancouver-bc?min-price=2000&box=x",
        "https://padmapper.com/?box=anything",
    ],
)
def test_is_url_allowed_rejects_robots_disallowed(url: str) -> None:
    assert is_url_allowed(url) is False, f"expected disallowed: {url}"


@pytest.mark.parametrize(
    "url",
    [
        "https://padmapper.com/apartments/vancouver-bc",
        "https://padmapper.com/apartments/vancouver-bc?min-price=2000&max-price=3000",
        "https://padmapper.com/rentals/some-listing-slug",
        "https://padmapper.com/buildings/some-building-slug",
    ],
)
def test_is_url_allowed_accepts_listing_pages(url: str) -> None:
    assert is_url_allowed(url) is True, f"expected allowed: {url}"


def test_is_url_allowed_does_not_match_apartments_prefix() -> None:
    """`Disallow: /api` should NOT also block `/apartments/...`."""
    assert is_url_allowed("https://padmapper.com/apartments/vancouver-bc") is True


# ---------------------------------------------------------------------------
# Health check — disallowed URLs and box= query params produce "blocked"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_ok_when_allowed() -> None:
    adapter, _ = _make_adapter(robots_allow=True)
    h = await adapter.health_check()
    assert h.status == "ok"
    assert h.name == "padmapper"


@pytest.mark.asyncio
async def test_health_check_blocked_when_robots_disallows() -> None:
    adapter, _ = _make_adapter(robots_allow=False)
    h = await adapter.health_check()
    assert h.status == "blocked"
    assert h.last_error == "robots.txt"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://padmapper.com/api/foo",
        "https://padmapper.com/apartments/vancouver-bc?box=1,2,3,4",
        "https://padmapper.com/buildings/x/cost-calculator",
    ],
)
async def test_fetch_blocks_disallowed_paths_and_box_param(url: str) -> None:
    adapter, fetcher = _make_adapter(robots_allow=True)
    with pytest.raises(RobotsDisallowedError):
        await adapter._fetch(url)
    assert fetcher.fetched_urls == [], "must not hit network for disallowed URLs"


# ---------------------------------------------------------------------------
# Search — synthetic fixture, scaffold returns []
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_uses_fixture_and_returns_empty_for_scaffold() -> None:
    html = (FIX / "search_page.html").read_text()
    adapter, fetcher = _make_adapter(html=html)
    results: list[RawListing] = []
    async for raw in adapter.search(NormalizedQuery(bedrooms_min=2, price_max=3000)):
        results.append(raw)
    assert results == []
    # The scaffold should have hit exactly one URL (the search page) and
    # that URL must NOT contain `box=`.
    assert len(fetcher.fetched_urls) == 1
    assert "box=" not in fetcher.fetched_urls[0]
    assert fetcher.fetched_urls[0].startswith("https://padmapper.com/apartments/vancouver-bc")


@pytest.mark.asyncio
async def test_search_url_never_includes_box_param() -> None:
    """No combination of NormalizedQuery filters can produce a `box=` URL."""
    adapter, _ = _make_adapter()
    queries = [
        NormalizedQuery(),
        NormalizedQuery(price_min=1500, price_max=4000),
        NormalizedQuery(bedrooms_min=1, bedrooms_max=3),
        NormalizedQuery(free_text_keywords=["balcony", "in-suite laundry"]),
        NormalizedQuery(neighborhoods=["Kitsilano", "Mount Pleasant"]),
    ]
    for q in queries:
        url = adapter._build_search_url(q)
        assert is_url_allowed(url), f"built disallowed URL: {url}"
        assert "box=" not in url


# ---------------------------------------------------------------------------
# Capabilities + protocol conformance
# ---------------------------------------------------------------------------


def test_capabilities_match_spec() -> None:
    adapter, _ = _make_adapter()
    assert adapter.capabilities["supported_filters"] == {
        "bedrooms_min",
        "bedrooms_max",
        "price_min",
        "price_max",
        "neighborhoods",
        "free_text_keywords",
    }


def test_rate_limit_at_or_below_one_per_second() -> None:
    adapter, _ = _make_adapter()
    assert adapter.rate_limit_per_second == 0.5


def test_user_agent_identifies_rentwise_not_chrome() -> None:
    adapter, _ = _make_adapter()
    assert "RentWise" in adapter.user_agent
    assert "Chrome" not in adapter.user_agent
    assert "Mozilla" not in adapter.user_agent


# ---------------------------------------------------------------------------
# Snippet length — even the stub must not produce >200-char snippets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_any_yielded_snippets_stay_under_200_chars() -> None:
    """The Pydantic model already enforces ≤200 chars; this test pins the
    contract for future implementations of _extract."""
    adapter, _ = _make_adapter(html="<html></html>")
    aiter_results: AsyncIterator[RawListing] = adapter.search(NormalizedQuery())
    async for raw in aiter_results:
        if raw.description_snippet is not None:
            assert len(raw.description_snippet) <= 200


# ---------------------------------------------------------------------------
# Registration — env flag gates _build_adapters
# ---------------------------------------------------------------------------


def test_adapter_not_registered_when_env_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from rentwise.http import search as search_module
    from rentwise.settings import settings

    # Ensure a clean cache and a known-disabled flag.
    search_module._build_adapters.cache_clear()
    monkeypatch.setattr(settings, "rentwise_padmapper_enabled", False)
    adapters = search_module._build_adapters()
    names = {a.name for a in adapters}
    assert "padmapper" not in names
    search_module._build_adapters.cache_clear()


def test_adapter_registered_when_env_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from rentwise.http import search as search_module
    from rentwise.settings import settings

    search_module._build_adapters.cache_clear()
    monkeypatch.setattr(settings, "rentwise_padmapper_enabled", True)
    try:
        adapters = search_module._build_adapters()
        names = {a.name for a in adapters}
        assert "padmapper" in names
    finally:
        search_module._build_adapters.cache_clear()
