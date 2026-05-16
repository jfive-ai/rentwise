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
