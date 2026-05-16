"""Tests for the fixture-backed demo adapter.

Demo mode is the fallback for sandboxed environments where the live sites
are unreachable. These tests verify:

- ``build_demo_adapters`` returns one adapter per supported source.
- Each adapter yields >=1 listing from its bundled fixture.
- ``health_check`` reports ``ok`` (no network).
- ``_build_adapters`` swaps in demo adapters when the flag is on.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import HttpUrl

from rentwise.adapters.base import SourceAdapter
from rentwise.adapters.demo import FixtureAdapter, build_demo_adapters
from rentwise.models import NormalizedQuery, RawListing

_EXPECTED_SOURCES = {"craigslist", "livrent", "rentals_ca", "padmapper", "zumper", "rew"}


def test_build_demo_adapters_covers_all_supported_sources() -> None:
    adapters = build_demo_adapters()
    names = {a.name for a in adapters}
    assert names == _EXPECTED_SOURCES


def test_demo_adapter_satisfies_protocol() -> None:
    adapter = FixtureAdapter(name="test", listings=[])
    assert isinstance(adapter, SourceAdapter)


@pytest.mark.asyncio
async def test_demo_adapters_each_yield_at_least_one_listing() -> None:
    adapters = build_demo_adapters()
    for adapter in adapters:
        listings: list[RawListing] = []
        async for raw in adapter.search(NormalizedQuery()):
            listings.append(raw)
        assert len(listings) >= 1, f"{adapter.name} should yield at least one demo listing"
        for raw in listings:
            assert raw.source == adapter.name
            assert str(raw.source_url).startswith("http")


@pytest.mark.asyncio
async def test_demo_health_check_is_ok() -> None:
    adapter = FixtureAdapter(
        name="test",
        listings=[
            RawListing(
                source="test",
                source_url=HttpUrl("https://example.com/1"),
                source_listing_id="1",
                title="t",
                posted_at=datetime.now(UTC),
            )
        ],
    )
    h = await adapter.health_check()
    assert h.status == "ok"


@pytest.mark.asyncio
async def test_fetch_listing_returns_match() -> None:
    sample = RawListing(
        source="test",
        source_url=HttpUrl("https://example.com/abc"),
        source_listing_id="abc",
        title="t",
        posted_at=datetime.now(UTC),
    )
    adapter = FixtureAdapter(name="test", listings=[sample])
    assert (await adapter.fetch_listing("abc")) is sample
    assert (await adapter.fetch_listing("missing")) is None


def _sample_listings() -> list[RawListing]:
    """Three rows: cheap-studio, mid-2BR, luxury-3BR. Covers price + bedroom bounds."""
    now = datetime.now(UTC)
    return [
        RawListing(
            source="demo",
            source_url=HttpUrl("https://example.com/1"),
            source_listing_id="1",
            title="Cozy studio downtown",
            address="100 Test St, Vancouver, BC",
            bedrooms=0.5,
            price_cad=1500,
            posted_at=now,
            description_snippet="Pet friendly, near transit",
        ),
        RawListing(
            source="demo",
            source_url=HttpUrl("https://example.com/2"),
            source_listing_id="2",
            title="Sunny 2BR in Kitsilano",
            address="200 Test Ave, Vancouver, BC",
            bedrooms=2,
            price_cad=2950,
            posted_at=now,
        ),
        RawListing(
            source="demo",
            source_url=HttpUrl("https://example.com/3"),
            source_listing_id="3",
            title="Luxury 3BR penthouse",
            address="300 Test Blvd, Vancouver, BC",
            bedrooms=3,
            price_cad=8500,
            posted_at=now,
        ),
    ]


async def _collect(adapter: FixtureAdapter, query: NormalizedQuery) -> list[RawListing]:
    out: list[RawListing] = []
    async for raw in adapter.search(query):
        out.append(raw)
    return out


@pytest.mark.asyncio
async def test_search_honors_price_max() -> None:
    """price_max must drop rows above the bound — the Codex review on PR #117
    flagged demo mode returning a $1.3M listing under a price_max=3000 filter
    because supported_filters was empty."""
    adapter = FixtureAdapter(name="demo", listings=_sample_listings())
    out = await _collect(adapter, NormalizedQuery(price_max=3000))
    assert [r.source_listing_id for r in out] == ["1", "2"]


@pytest.mark.asyncio
async def test_search_honors_price_min() -> None:
    adapter = FixtureAdapter(name="demo", listings=_sample_listings())
    out = await _collect(adapter, NormalizedQuery(price_min=2000))
    assert [r.source_listing_id for r in out] == ["2", "3"]


@pytest.mark.asyncio
async def test_search_honors_bedrooms_bounds() -> None:
    adapter = FixtureAdapter(name="demo", listings=_sample_listings())
    out = await _collect(adapter, NormalizedQuery(bedrooms_min=2, bedrooms_max=2))
    assert [r.source_listing_id for r in out] == ["2"]


@pytest.mark.asyncio
async def test_search_honors_free_text_keywords_and() -> None:
    """All keywords must appear; substring match across title/address/snippet."""
    adapter = FixtureAdapter(name="demo", listings=_sample_listings())
    out = await _collect(adapter, NormalizedQuery(free_text_keywords=["pet", "transit"]))
    assert [r.source_listing_id for r in out] == ["1"]
    out = await _collect(adapter, NormalizedQuery(free_text_keywords=["nonexistent"]))
    assert out == []


@pytest.mark.asyncio
async def test_search_drops_rows_with_missing_price_when_price_filter_set() -> None:
    """A row without ``price_cad`` can't be confirmed to satisfy a price
    bound, so it's dropped — matches the "stricter than the user asked"
    interpretation we use for unknown values."""
    now = datetime.now(UTC)
    rows = [
        RawListing(
            source="demo",
            source_url=HttpUrl("https://example.com/np"),
            source_listing_id="np",
            title="No price row",
            posted_at=now,
        ),
    ]
    adapter = FixtureAdapter(name="demo", listings=rows)
    assert await _collect(adapter, NormalizedQuery()) == rows
    assert await _collect(adapter, NormalizedQuery(price_max=3000)) == []


@pytest.mark.asyncio
async def test_capabilities_declare_filterable_fields() -> None:
    """Aggregator strips fields the adapter doesn't declare. Demo must
    declare the filters it honors so `project_query_to_capabilities` lets
    them through."""
    adapter = FixtureAdapter(name="demo", listings=[])
    supported = adapter.capabilities["supported_filters"]
    assert {"price_min", "price_max", "bedrooms_min", "bedrooms_max"} <= supported


def test_demo_mode_swaps_adapters_in_build(monkeypatch: pytest.MonkeyPatch) -> None:
    from rentwise.http import search as search_module
    from rentwise.settings import settings

    monkeypatch.setattr(settings, "rentwise_demo_mode", True)
    search_module._build_adapters.cache_clear()
    try:
        adapters = search_module._build_adapters()
        names = {a.name for a in adapters}
        assert names == _EXPECTED_SOURCES
    finally:
        search_module._build_adapters.cache_clear()
