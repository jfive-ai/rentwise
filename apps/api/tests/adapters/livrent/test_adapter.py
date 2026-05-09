"""Tests for the liv.rent adapter (calibrated against live HTML, #105).

The fixture is a trimmed snippet of the live ``rental-listings/city/vancouver``
page rendered via Playwright (two real listing anchors with ``srcset`` stripped
to keep the file small). When the live DOM drifts, recapture and re-trim
rather than synthesizing a stand-in.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from rentwise.adapters.base import RobotsDisallowedError, SourceAdapter
from rentwise.adapters.livrent.adapter import LivRentAdapter
from rentwise.adapters.playwright_fetcher import PlaywrightFetcher
from rentwise.models import NormalizedQuery

FIX = Path(__file__).resolve().parent / "fixtures"


def _make_fetcher(html: str, *, robots_allowed: bool = True) -> PlaywrightFetcher:
    fetcher = PlaywrightFetcher(user_agent="RentWise-test/0.1", jitter_ms=(0, 0))
    fetcher.robots.is_allowed = AsyncMock(return_value=robots_allowed)  # type: ignore[method-assign]
    fetcher.fetch_html = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda url, wait_for=None: (
            html
            if robots_allowed
            else (_ for _ in ()).throw(RobotsDisallowedError(f"robots blocks {url}"))
        )
    )
    return fetcher


@pytest.fixture
def fixture_html() -> str:
    return (FIX / "search_page.html").read_text()


def test_satisfies_source_adapter_protocol() -> None:
    adapter = LivRentAdapter(user_agent="RentWise-test/0.1")
    assert isinstance(adapter, SourceAdapter)
    assert adapter.name == "livrent"
    assert adapter.method == "browser"
    assert adapter.rate_limit_per_second == 0.5
    assert adapter.base_url == "https://liv.rent"


def test_extractor_marked_calibrated() -> None:
    """Aggregator only suppresses the "scaffold not calibrated" health
    warning when this flag is True (#94, #105). Failure here means the
    adapter is wired but the aggregator will still report degraded."""
    assert LivRentAdapter.is_extractor_calibrated is True


@pytest.mark.asyncio
async def test_search_extracts_real_listings_from_fixture(fixture_html: str) -> None:
    fetcher = _make_fetcher(fixture_html, robots_allowed=True)
    adapter = LivRentAdapter(user_agent="RentWise-test/0.1", fetcher=fetcher)
    results = [r async for r in adapter.search(NormalizedQuery())]
    assert len(results) == 2

    by_id = {r.source_listing_id: r for r in results}
    assert set(by_id) == {"142215", "141116"}

    a = by_id["142215"]
    assert a.source == "livrent"
    assert str(a.source_url) == "https://liv.rent/rental-listings/detail/house/vancouver/142215"
    assert a.price_cad == 3000
    assert a.bedrooms == 2.0
    assert a.bathrooms == 1.0
    assert a.address == "Puget Dr, Vancouver, BC"
    assert len(a.photos) == 1
    assert "cdn.liv.rent" in str(a.photos[0])

    b = by_id["141116"]
    assert b.price_cad == 3995
    assert b.bedrooms == 3.0
    assert b.bathrooms == 2.0
    assert b.address == "8080 Nunavut Lane, Vancouver, BC"


@pytest.mark.asyncio
async def test_search_raises_on_robots_disallow() -> None:
    fetcher = _make_fetcher("", robots_allowed=False)
    adapter = LivRentAdapter(user_agent="RentWise-test/0.1", fetcher=fetcher)
    with pytest.raises(RobotsDisallowedError):
        async for _ in adapter.search(NormalizedQuery()):
            pass


@pytest.mark.asyncio
async def test_health_check_blocked_when_robots_disallows() -> None:
    fetcher = _make_fetcher("", robots_allowed=False)
    adapter = LivRentAdapter(user_agent="RentWise-test/0.1", fetcher=fetcher)
    h = await adapter.health_check()
    assert h.status == "blocked"
    assert h.last_error == "robots.txt"


@pytest.mark.asyncio
async def test_search_returns_empty_when_dom_drifts() -> None:
    """Defensive: an unrecognized HTML page shouldn't crash the adapter,
    it should just yield nothing. This is the fallback the aggregator's
    `degraded` health path relies on."""
    fetcher = _make_fetcher("<html><body>no listings here</body></html>", robots_allowed=True)
    adapter = LivRentAdapter(user_agent="RentWise-test/0.1", fetcher=fetcher)
    results = [r async for r in adapter.search(NormalizedQuery())]
    assert results == []


def test_disabled_by_default_not_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutate the live settings instance + clear the lru_cache, rather than
    reloading modules — module reload pollutes shared state across the
    rest of the test session."""
    from rentwise.http import search as search_module
    from rentwise.settings import settings

    monkeypatch.setattr(settings, "rentwise_livrent_enabled", False)
    search_module._build_adapters.cache_clear()
    try:
        adapters = search_module._build_adapters()
        assert all(a.name != "livrent" for a in adapters)
    finally:
        search_module._build_adapters.cache_clear()


def test_enabled_registers_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    from rentwise.http import search as search_module
    from rentwise.settings import settings

    monkeypatch.setattr(settings, "rentwise_livrent_enabled", True)
    search_module._build_adapters.cache_clear()
    try:
        adapters = search_module._build_adapters()
        assert any(a.name == "livrent" for a in adapters)
    finally:
        search_module._build_adapters.cache_clear()


@pytest.mark.asyncio
async def test_extracted_snippets_capped_at_200_chars(fixture_html: str) -> None:
    fetcher = _make_fetcher(fixture_html, robots_allowed=True)
    adapter = LivRentAdapter(user_agent="RentWise-test/0.1", fetcher=fetcher)
    async for raw in adapter.search(NormalizedQuery()):
        if raw.description_snippet is not None:
            assert len(raw.description_snippet) <= 200
