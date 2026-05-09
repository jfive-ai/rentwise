"""AggregatorService unit tests with a fake adapter (no httpx)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import ClassVar

import pytest
from pydantic import HttpUrl

from rentwise.adapters.base import AdapterCapabilities
from rentwise.aggregator.service import AggregatorService
from rentwise.models import (
    AdapterHealth,
    NormalizedQuery,
    PetPolicy,
    RawListing,
    SearchRequest,
    SortOrder,
)


class FakeAdapter:
    name = "craigslist"
    base_url = "https://vancouver.craigslist.org"
    method = "rss"
    rate_limit_per_second = 1.0
    capabilities: ClassVar[AdapterCapabilities] = {
        "supported_filters": {"bedrooms_min", "price_max", "free_text_keywords"}
    }

    def __init__(self, listings: list[RawListing], should_raise: Exception | None = None):
        self._listings = listings
        self._should_raise = should_raise
        self.calls = 0

    async def search(self, query: NormalizedQuery) -> AsyncIterator[RawListing]:
        self.calls += 1
        if self._should_raise is not None:
            raise self._should_raise
        for x in self._listings:
            yield x

    async def fetch_listing(self, listing_id: str):
        return None

    async def health_check(self) -> AdapterHealth:
        return AdapterHealth(name=self.name, status="ok")


def _raw(i: int, *, posted: datetime | None = None) -> RawListing:
    return RawListing(
        source="craigslist",
        source_url=HttpUrl(f"https://example.com/{i}"),
        source_listing_id=str(i),
        title=f"$2000 / 1br - listing {i}",
        bedrooms=1.0,
        price_cad=2000,
        posted_at=posted or datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_cache_miss_fetches_and_persists(session):
    adapter = FakeAdapter(listings=[_raw(1), _raw(2)])
    svc = AggregatorService(adapters=[adapter], session=session, cache_ttl_seconds=900)
    req = SearchRequest(query=NormalizedQuery(bedrooms_min=1))
    resp = await svc.search(req)
    await session.commit()

    assert resp.cache_status == "miss"
    assert len(resp.listings) == 2
    assert adapter.calls == 1


@pytest.mark.asyncio
async def test_cache_hit_does_not_call_adapter(session):
    adapter = FakeAdapter(listings=[_raw(1)])
    svc = AggregatorService(adapters=[adapter], session=session, cache_ttl_seconds=900)
    req = SearchRequest(query=NormalizedQuery(bedrooms_min=1))
    await svc.search(req)
    await session.commit()
    adapter.calls = 0  # reset
    resp = await svc.search(req)
    assert resp.cache_status == "fresh"
    assert adapter.calls == 0


@pytest.mark.asyncio
async def test_force_refresh_bypasses_cache(session):
    adapter = FakeAdapter(listings=[_raw(1)])
    svc = AggregatorService(adapters=[adapter], session=session, cache_ttl_seconds=900)
    req = SearchRequest(query=NormalizedQuery(bedrooms_min=1))
    await svc.search(req)
    await session.commit()

    req_force = SearchRequest(query=NormalizedQuery(bedrooms_min=1), force_refresh=True)
    resp = await svc.search(req_force)
    assert resp.cache_status == "miss"
    assert adapter.calls == 2


@pytest.mark.asyncio
async def test_unsupported_filters_reported(session):
    adapter = FakeAdapter(listings=[_raw(1)])
    svc = AggregatorService(adapters=[adapter], session=session, cache_ttl_seconds=900)
    # `pets` is genuinely unsupported (no adapter handles it).
    # `school_catchment` is handled by the aggregator's post-filter as of
    # PR-B, so it must NOT appear in unsupported_filters even though no
    # adapter declares support for it.
    req = SearchRequest(
        query=NormalizedQuery(bedrooms_min=1, pets=PetPolicy.OK, school_catchment="Byng")
    )
    resp = await svc.search(req)
    assert "pets" in resp.unsupported_filters
    assert "school_catchment" not in resp.unsupported_filters
    assert "transit_max_walk_minutes" not in resp.unsupported_filters


@pytest.mark.asyncio
async def test_adapter_exception_marks_degraded_and_returns_partial(session):
    adapter = FakeAdapter(listings=[], should_raise=RuntimeError("boom"))
    svc = AggregatorService(adapters=[adapter], session=session, cache_ttl_seconds=900)
    resp = await svc.search(SearchRequest(query=NormalizedQuery()))
    await session.commit()
    assert resp.listings == []
    assert resp.source_health["craigslist"].status == "degraded"


@pytest.mark.asyncio
async def test_sort_price_asc(session):
    adapter = FakeAdapter(
        listings=[
            RawListing(
                source="craigslist",
                source_url=HttpUrl("https://x/2"),
                source_listing_id="2",
                title="$3000",
                price_cad=3000,
                posted_at=datetime.now(UTC),
            ),
            RawListing(
                source="craigslist",
                source_url=HttpUrl("https://x/1"),
                source_listing_id="1",
                title="$1500",
                price_cad=1500,
                posted_at=datetime.now(UTC),
            ),
        ]
    )
    svc = AggregatorService(adapters=[adapter], session=session, cache_ttl_seconds=900)
    resp = await svc.search(SearchRequest(query=NormalizedQuery(), sort=SortOrder.PRICE_ASC))
    assert [x.price_cad for x in resp.listings] == [1500, 3000]


@pytest.mark.asyncio
async def test_all_adapters_failing_does_not_poison_cache(session):
    """Regression: previously an all-fail run would write listing_ids=[] as fresh,
    masking the outage for the full TTL on the next call."""
    adapter = FakeAdapter(listings=[], should_raise=RuntimeError("network down"))
    svc = AggregatorService(adapters=[adapter], session=session, cache_ttl_seconds=900)
    await svc.search(SearchRequest(query=NormalizedQuery()))
    await session.commit()

    # If we hit /search again, the adapter must be called again — not served from a poisoned fresh cache.
    adapter.calls = 0
    resp = await svc.search(SearchRequest(query=NormalizedQuery()))
    assert adapter.calls == 1, "second call must retry, not serve poisoned empty cache"
    assert resp.cache_status == "miss"
    assert resp.source_health["craigslist"].status == "degraded"


def _raw_at(i: int, *, lat: float | None, lon: float | None) -> RawListing:
    return RawListing(
        source="craigslist",
        source_url=HttpUrl(f"https://example.com/{i}"),
        source_listing_id=str(i),
        title=f"$2000 / 1br - listing {i}",
        bedrooms=1.0,
        price_cad=2000,
        posted_at=datetime.now(UTC),
        lat=lat,
        lon=lon,
    )


@pytest.mark.asyncio
async def test_neighborhood_filter_drops_listings_outside_polygon(session):
    """`neighborhoods=["Dunbar"]` must reject listings that the wide
    Craigslist FSA-radius search dragged in from Burnaby / Richmond /
    Kitsilano. (#92)
    """
    inside_dunbar = _raw_at(1, lat=49.255, lon=-123.185)  # 4750 W 16th area
    inside_kits = _raw_at(2, lat=49.268, lon=-123.165)
    outside_city = _raw_at(3, lat=49.226, lon=-122.998)  # Metrotown
    no_coords = _raw_at(4, lat=None, lon=None)

    adapter = FakeAdapter(listings=[inside_dunbar, inside_kits, outside_city, no_coords])
    svc = AggregatorService(adapters=[adapter], session=session, cache_ttl_seconds=900)
    req = SearchRequest(query=NormalizedQuery(neighborhoods=["Dunbar"]))
    resp = await svc.search(req)
    await session.commit()

    ids = {x.source_listing_id for x in resp.listings}
    assert ids == {"1"}, f"only the in-polygon listing should survive; got {ids}"
    assert "neighborhoods" not in resp.unsupported_filters


@pytest.mark.asyncio
async def test_neighborhood_alias_point_grey_resolves(session):
    """`Point Grey` → `West Point Grey` polygon."""
    inside_pt_grey = _raw_at(1, lat=49.265, lon=-123.205)
    inside_kits = _raw_at(2, lat=49.268, lon=-123.165)
    adapter = FakeAdapter(listings=[inside_pt_grey, inside_kits])
    svc = AggregatorService(adapters=[adapter], session=session, cache_ttl_seconds=900)
    resp = await svc.search(SearchRequest(query=NormalizedQuery(neighborhoods=["Point Grey"])))
    await session.commit()
    assert {x.source_listing_id for x in resp.listings} == {"1"}


@pytest.mark.asyncio
async def test_all_adapters_failing_falls_back_to_stale_cache(session):
    """If a previous successful search left a stale cache, an all-fail run returns the stale
    listings tagged cache_status="stale" with degraded source_health — better than serving nothing."""
    good_adapter = FakeAdapter(listings=[_raw(1)])
    svc_ok = AggregatorService(
        adapters=[good_adapter], session=session, cache_ttl_seconds=0
    )  # immediately stale
    await svc_ok.search(SearchRequest(query=NormalizedQuery()))
    await session.commit()

    bad_adapter = FakeAdapter(listings=[], should_raise=RuntimeError("network down"))
    svc_bad = AggregatorService(adapters=[bad_adapter], session=session, cache_ttl_seconds=0)
    resp = await svc_bad.search(SearchRequest(query=NormalizedQuery()))
    assert resp.cache_status == "stale"
    assert len(resp.listings) == 1
    assert resp.source_health["craigslist"].status == "degraded"
