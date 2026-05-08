"""Rentals.ca scaffold adapter tests.

All HTML inputs are synthetic — the live site is never fetched. See
`fixtures/search_page.html` for the structure these tests calibrate against.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import respx
from httpx import Response

from rentwise.adapters.rentalsca.adapter import (
    RentalsCaAdapter,
    _build_search_url,
)
from rentwise.models import NormalizedQuery

FIX = Path(__file__).resolve().parent / "fixtures"
SEARCH_HTML = (FIX / "search_page.html").read_text()


@pytest.fixture
def adapter() -> RentalsCaAdapter:
    """Adapter with no Playwright fetcher; tests inject one when needed."""
    return RentalsCaAdapter(user_agent="RentWise-test/0.1", jitter_ms=(0, 0))


# ---------------------------------------------------------------------------
# Protocol contract
# ---------------------------------------------------------------------------


def test_adapter_metadata(adapter: RentalsCaAdapter) -> None:
    assert adapter.name == "rentals_ca"
    assert adapter.base_url == "https://rentals.ca"
    assert adapter.method == "browser"
    # Operational rule: never above 1.0; we pick 0.5.
    assert adapter.rate_limit_per_second == 0.5
    assert adapter.rate_limit_per_second <= 1.0


def test_capabilities_match_spec(adapter: RentalsCaAdapter) -> None:
    caps = adapter.capabilities
    assert caps["supported_filters"] == {
        "bedrooms_min",
        "bedrooms_max",
        "price_min",
        "price_max",
    }


# ---------------------------------------------------------------------------
# URL builder — never includes robots.txt-disallowed params.
# ---------------------------------------------------------------------------


def test_search_url_omits_disallowed_params() -> None:
    q = NormalizedQuery(price_min=1500, price_max=3000, bedrooms_min=1, bedrooms_max=2)
    url = _build_search_url(q)
    assert url.startswith("https://rentals.ca/vancouver")
    for forbidden in ("bbox=", "amenities=", "types=", "-feed.json", "-feed.xml"):
        assert forbidden not in url, f"URL leaked disallowed token: {forbidden!r} in {url}"
    # Allowed params survive.
    assert "min_price=1500" in url
    assert "max_price=3000" in url


def test_search_url_no_params_when_query_empty() -> None:
    url = _build_search_url(NormalizedQuery())
    assert url == "https://rentals.ca/vancouver"


# ---------------------------------------------------------------------------
# Synthetic-fixture extraction
# ---------------------------------------------------------------------------


def test_extract_parses_synthetic_fixture(adapter: RentalsCaAdapter) -> None:
    listings = adapter._extract(SEARCH_HTML)
    assert len(listings) == 2

    first = listings[0]
    assert first.source == "rentals_ca"
    assert first.source_listing_id == "abc123"
    assert str(first.source_url) == "https://rentals.ca/vancouver/abc123-kitsilano-2br"
    assert first.title == "Bright 2BR in Kitsilano"
    assert first.address == "1234 W 4th Ave, Vancouver, BC"
    assert first.price_cad == 2950
    assert first.bedrooms == 2.0
    assert len(first.photos) == 1
    assert str(first.photos[0]) == "https://images.rentals.ca/abc123/cover.jpg"

    second = listings[1]
    assert second.source_listing_id == "def456"
    assert second.bedrooms == 0.5  # studio
    # Photo URL was relative in the fixture; must be absolutized.
    assert str(second.photos[0]) == "https://rentals.ca/images/def456/cover.jpg"


def test_snippet_truncated_to_200_chars(adapter: RentalsCaAdapter) -> None:
    listings = adapter._extract(SEARCH_HTML)
    long_one = listings[1]
    assert long_one.description_snippet is not None
    assert len(long_one.description_snippet) <= 200, (
        f"snippet leaked past 200 chars: {len(long_one.description_snippet)}"
    )


def test_extract_returns_empty_with_warning_on_unknown_markup(
    adapter: RentalsCaAdapter,
) -> None:
    """Scaffold honesty: if no cards match, we log and bail rather than guess."""
    listings = adapter._extract("<html><body><div>nothing here</div></body></html>")
    assert listings == []


# ---------------------------------------------------------------------------
# search() — wired against a fake fetcher so we never touch real Playwright.
# ---------------------------------------------------------------------------


class _FakeFetcher:
    """Stand-in for PlaywrightFetcher; returns canned HTML."""

    def __init__(self, html: str) -> None:
        self.html = html
        self.calls: list[tuple[str, str | None]] = []

    async def fetch_html(self, url: str, *, wait_for: str | None = None) -> str:
        self.calls.append((url, wait_for))
        return self.html

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_search_yields_listings_from_fake_fetcher(
    adapter: RentalsCaAdapter,
) -> None:
    fake = _FakeFetcher(SEARCH_HTML)
    adapter._fetcher = fake  # type: ignore[assignment]
    adapter.robots.is_allowed = AsyncMock(return_value=True)  # type: ignore[method-assign]

    results = [r async for r in adapter.search(NormalizedQuery(bedrooms_min=1))]

    assert len(results) == 2
    assert all(r.source == "rentals_ca" for r in results)
    # We asked Playwright to wait for the listing-card element.
    assert fake.calls and fake.calls[0][1] is not None
    assert "listing-card" in fake.calls[0][1]


@pytest.mark.asyncio
async def test_search_returns_empty_when_robots_disallows(
    adapter: RentalsCaAdapter,
) -> None:
    fake = _FakeFetcher(SEARCH_HTML)
    adapter._fetcher = fake  # type: ignore[assignment]
    adapter.robots.is_allowed = AsyncMock(return_value=False)  # type: ignore[method-assign]

    results = [r async for r in adapter.search(NormalizedQuery())]

    assert results == []
    # The fetcher must NOT have been invoked when robots disallows.
    assert fake.calls == []


# ---------------------------------------------------------------------------
# health_check — robots check + httpx probe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_blocked_when_robots_disallows(
    adapter: RentalsCaAdapter,
) -> None:
    adapter.robots.is_allowed = AsyncMock(return_value=False)  # type: ignore[method-assign]
    h = await adapter.health_check()
    assert h.status == "blocked"
    assert h.last_error == "robots.txt"


@pytest.mark.asyncio
async def test_health_check_blocked_on_403(adapter: RentalsCaAdapter) -> None:
    adapter.robots.is_allowed = AsyncMock(return_value=True)  # type: ignore[method-assign]
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://rentals.ca/vancouver").mock(return_value=Response(403))
        h = await adapter.health_check()
    assert h.status == "blocked"
    assert "403" in (h.last_error or "")


@pytest.mark.asyncio
async def test_health_check_blocked_on_429(adapter: RentalsCaAdapter) -> None:
    adapter.robots.is_allowed = AsyncMock(return_value=True)  # type: ignore[method-assign]
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://rentals.ca/vancouver").mock(return_value=Response(429))
        h = await adapter.health_check()
    assert h.status == "blocked"


@pytest.mark.asyncio
async def test_health_check_ok_on_200(adapter: RentalsCaAdapter) -> None:
    adapter.robots.is_allowed = AsyncMock(return_value=True)  # type: ignore[method-assign]
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://rentals.ca/vancouver").mock(
            return_value=Response(200, text="<html></html>")
        )
        h = await adapter.health_check()
    assert h.status == "ok"


# ---------------------------------------------------------------------------
# Registration is gated by RENTWISE_RENTALSCA_ENABLED.
# ---------------------------------------------------------------------------


def test_adapter_not_registered_when_env_var_disabled() -> None:
    from rentwise.http import search as search_module

    search_module._build_adapters.cache_clear()
    with patch.object(search_module.settings, "rentwise_rentalsca_enabled", False):
        adapters = search_module._build_adapters()
    search_module._build_adapters.cache_clear()
    assert all(a.name != "rentals_ca" for a in adapters), (
        "RentalsCaAdapter must NOT be registered when the env flag is False."
    )


def test_adapter_registered_when_env_var_enabled() -> None:
    from rentwise.http import search as search_module

    search_module._build_adapters.cache_clear()
    with patch.object(search_module.settings, "rentwise_rentalsca_enabled", True):
        adapters = search_module._build_adapters()
    search_module._build_adapters.cache_clear()
    assert any(a.name == "rentals_ca" for a in adapters)


def test_default_settings_keep_adapter_disabled() -> None:
    """Belt-and-suspenders: the in-process settings default must be False."""
    from rentwise.settings import Settings

    s = Settings()
    assert s.rentwise_rentalsca_enabled is False
