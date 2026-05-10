"""Tests for the streaming /search aggregator (issue #113).

Asserts:
- Listings stream out incrementally (not all at the end).
- Adapters run in parallel — total elapsed < sum of per-adapter delays.
- Per-adapter failures don't bring the whole stream down.
- ``adapter_done`` events report the right status (ok / degraded /
  scaffold-degraded for empty uncalibrated adapters).
- ``complete`` event carries source_health for every adapter.
- Cache hit short-circuits (no adapter calls).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import ClassVar

import pytest
from pydantic import HttpUrl
from sqlalchemy.ext.asyncio import async_sessionmaker

from rentwise.adapters.base import AdapterCapabilities
from rentwise.adapters.scaffold_base import ScaffoldAdapterBase
from rentwise.aggregator.streaming import stream_search
from rentwise.dedup.service import DedupConfig
from rentwise.enrichment.neighborhoods import NeighborhoodLookup
from rentwise.enrichment.service import EnrichmentConfig
from rentwise.models import (
    AdapterHealth,
    NormalizedQuery,
    RawListing,
    SearchRequest,
)


class FakeAdapter:
    name = "craigslist"
    base_url = "https://vancouver.craigslist.org"
    method = "rss"
    rate_limit_per_second = 1.0
    capabilities: ClassVar[AdapterCapabilities] = {
        "supported_filters": {"bedrooms_min", "price_max"}
    }

    def __init__(
        self,
        listings: list[RawListing],
        *,
        delay_per_listing: float = 0.0,
        should_raise: Exception | None = None,
        name: str | None = None,
    ) -> None:
        self._listings = listings
        self._delay = delay_per_listing
        self._raise = should_raise
        if name is not None:
            self.name = name

    async def search(self, query: NormalizedQuery) -> AsyncIterator[RawListing]:
        if self._raise is not None:
            raise self._raise
        for x in self._listings:
            if self._delay > 0:
                await asyncio.sleep(self._delay)
            yield x

    async def fetch_listing(self, listing_id: str):
        return None

    async def health_check(self) -> AdapterHealth:
        return AdapterHealth(name=self.name, status="ok")


def _raw(i: int, source: str = "craigslist") -> RawListing:
    return RawListing(
        source=source,
        source_url=HttpUrl(f"https://example.com/{source}/{i}"),
        source_listing_id=f"{source}-{i}",
        title=f"$2000 / 1br - listing {i}",
        bedrooms=1.0,
        price_cad=2000,
        posted_at=datetime.now(UTC),
    )


@pytest.fixture
def smaker(migrated_engine) -> async_sessionmaker:
    """Per-task sessionmaker — the streaming aggregator hands one of
    these to each adapter task so AsyncSessions aren't shared across
    coroutines (which SQLAlchemy doesn't support)."""
    return async_sessionmaker(migrated_engine, expire_on_commit=False)


class _StubGeocoder:
    async def geocode(self, query: str):
        return None


class _StubPhotoHasher:
    async def hash_url(self, url: str):
        return None


def _kwargs(smaker, adapters, *, query=None, force_refresh=False):
    return dict(
        req=SearchRequest(query=query or NormalizedQuery(), force_refresh=force_refresh),
        adapters=adapters,
        sessionmaker=smaker,
        cache_ttl_seconds=900,
        enrichment_config=EnrichmentConfig(
            enabled=False,  # tests don't need real geocoding
            photo_hash_enabled=False,
        ),
        dedup_config=DedupConfig(enabled=False),
        geocoder=_StubGeocoder(),
        photo_hasher=_StubPhotoHasher(),
        neighborhoods=NeighborhoodLookup(),
    )


@pytest.mark.asyncio
async def test_stream_emits_started_listing_done_complete(smaker):
    adapter = FakeAdapter([_raw(1), _raw(2)])
    events = []
    async for ev in stream_search(**_kwargs(smaker, [adapter])):
        events.append(ev)

    types = [e["event"] for e in events]
    assert types[0] == "started"
    assert types[-1] == "complete"
    listing_count = sum(1 for t in types if t == "listing")
    assert listing_count == 2
    done_events = [e for e in events if e["event"] == "adapter_done"]
    assert len(done_events) == 1
    assert done_events[0]["adapter"] == "craigslist"
    assert done_events[0]["count"] == 2


@pytest.mark.asyncio
async def test_stream_listings_arrive_incrementally(smaker):
    """A 5-listing adapter with 50ms gaps must emit listings spread over
    time, not all at the final tick. Asserts the stream is genuinely
    incremental, not buffered.
    """
    adapter = FakeAdapter([_raw(i) for i in range(5)], delay_per_listing=0.05)
    timestamps: list[float] = []
    loop = asyncio.get_running_loop()
    start = loop.time()
    async for ev in stream_search(**_kwargs(smaker, [adapter])):
        if ev["event"] == "listing":
            timestamps.append(loop.time() - start)

    assert len(timestamps) == 5
    # First listing must not arrive *with* the last one. We allow
    # generous slack — the assertion is only "not all at once."
    spread = timestamps[-1] - timestamps[0]
    assert spread > 0.05, f"listings buffered, no incremental delivery (spread={spread:.3f}s)"


@pytest.mark.asyncio
async def test_adapters_run_in_parallel(smaker):
    """Two adapters each yielding one listing after a 0.3s sleep should
    finish in <0.5s total — proves they run in parallel rather than serial.
    """
    a1 = FakeAdapter([_raw(1, "craigslist")], delay_per_listing=0.3, name="craigslist")
    a2 = FakeAdapter([_raw(2, "padmapper")], delay_per_listing=0.3, name="padmapper")

    loop = asyncio.get_running_loop()
    start = loop.time()
    listings: list[dict] = []
    async for ev in stream_search(**_kwargs(smaker, [a1, a2])):
        if ev["event"] == "listing":
            listings.append(ev)
    elapsed = loop.time() - start

    assert len(listings) == 2
    # Serial would be ~0.6s; parallel ~0.3s. We assert <0.5s.
    assert elapsed < 0.5, f"adapters not parallel (elapsed {elapsed:.3f}s)"


@pytest.mark.asyncio
async def test_adapter_failure_does_not_stop_other_adapters(smaker):
    a_ok = FakeAdapter([_raw(1)], name="craigslist")
    a_bad = FakeAdapter([_raw(2, "padmapper")], should_raise=RuntimeError("boom"), name="padmapper")

    events = []
    async for ev in stream_search(**_kwargs(smaker, [a_ok, a_bad])):
        events.append(ev)

    listings = [e for e in events if e["event"] == "listing"]
    assert len(listings) == 1  # the OK adapter still emits

    done_events = {e["adapter"]: e for e in events if e["event"] == "adapter_done"}
    assert done_events["craigslist"]["status"] == "ok"
    assert done_events["padmapper"]["status"] == "degraded"
    assert "boom" in (done_events["padmapper"]["error"] or "")

    complete = next(e for e in events if e["event"] == "complete")
    assert "padmapper" in complete["source_health"]
    assert "craigslist" in complete["source_health"]


@pytest.mark.asyncio
async def test_uncalibrated_scaffold_with_zero_yields_reports_degraded(smaker):
    """An empty result from a scaffold adapter must surface as
    ``status='degraded'`` with the scaffold note — the user needs to see
    *why* nothing came back from an enabled source (#94 contract)."""

    class _SilentScaffold(ScaffoldAdapterBase):
        name: str = "silent-scaffold"
        base_url: str = "https://example.test"

        async def search(self, query: NormalizedQuery):  # type: ignore[override]
            if False:
                yield None  # type: ignore[unreachable]
            return

    adapter = _SilentScaffold(user_agent="RentWise/test")
    events = []
    async for ev in stream_search(**_kwargs(smaker, [adapter])):
        events.append(ev)

    done = next(e for e in events if e["event"] == "adapter_done")
    assert done["status"] == "degraded"
    assert "scaffold" in (done["error"] or "")


@pytest.mark.asyncio
async def test_cache_hit_short_circuits_adapter_call(smaker):
    """A second stream for the same query, within TTL, must not re-call
    adapters — the cache row is reused and its listings replayed."""
    adapter = FakeAdapter([_raw(1), _raw(2)])
    # First run populates the cache.
    async for _ev in stream_search(**_kwargs(smaker, [adapter])):
        pass

    # Second run: replace the adapter with one that would explode if called.
    explosive = FakeAdapter([], should_raise=AssertionError("must not be called on cache hit"))
    events = []
    async for ev in stream_search(**_kwargs(smaker, [explosive])):
        events.append(ev)

    complete = next(e for e in events if e["event"] == "complete")
    assert complete["cache_status"] == "fresh"
    assert complete["total"] == 2
