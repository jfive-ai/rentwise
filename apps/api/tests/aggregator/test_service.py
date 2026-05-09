"""AggregatorService unit tests with a fake adapter (no httpx)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import ClassVar

import pytest
from pydantic import HttpUrl

from rentwise.adapters.base import AdapterCapabilities
from rentwise.adapters.scaffold_base import ScaffoldAdapterBase
from rentwise.aggregator.service import (
    AggregatorService,
    _catchment_matches,
    _is_uncalibrated_scaffold,
)
from rentwise.models import (
    AdapterHealth,
    NormalizedListing,
    NormalizedQuery,
    PetPolicy,
    RawListing,
    SchoolCatchments,
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


def _listing(
    *,
    title: str = "Sunny 1br",
    address: str | None = None,
    description: str | None = None,
    catchments: SchoolCatchments | None = None,
) -> NormalizedListing:
    from datetime import datetime as _dt
    from uuid import uuid4 as _uuid4

    new_id = _uuid4()
    return NormalizedListing(
        id=new_id,
        canonical_id=new_id,
        source="craigslist",
        source_url=HttpUrl("https://example.com/1"),
        source_listing_id="1",
        title=title,
        address=address,
        address_normalized=None,
        lat=None,
        lon=None,
        bedrooms=1.0,
        bathrooms=None,
        price_cad=2000,
        pets_allowed=None,
        furnished=None,
        available_date=None,
        posted_at=_dt.now(UTC),
        last_seen_at=_dt.now(UTC),
        photos=[],
        description_snippet=description,
        school_catchments=catchments or SchoolCatchments(),
    )


def test_catchment_match_uses_address_when_enriched():
    """Geocoded listing inside Byng polygon → enrichment populated
    secondary='Lord Byng'; needle 'lord byng' matches (#93)."""
    listing = _listing(
        title="Quiet 2br near 16th and Crown",
        catchments=SchoolCatchments(secondary="Lord Byng"),
    )
    assert _catchment_matches(listing, "lord byng") is True


def test_catchment_drops_listing_outside_polygon_even_if_title_mentions_school():
    """Geocoded listing whose secondary != 'Lord Byng' (e.g. Kitsilano) is
    dropped even if title mentions Byng — text without address-confirmation
    isn't enough when address-confirmation contradicts it (#93)."""
    listing = _listing(
        title="Walk to Lord Byng — but actually in Kitsilano",
        catchments=SchoolCatchments(secondary="Kitsilano"),
    )
    assert _catchment_matches(listing, "lord byng") is False


def test_catchment_falls_back_to_text_when_no_geocode():
    """Listing has no enriched catchment (no geocode); fall back to a
    text match against title + address + description (#93)."""
    listing = _listing(
        title="Bright suite — Lord Byng catchment per landlord",
        catchments=SchoolCatchments(),  # empty
    )
    assert _catchment_matches(listing, "lord byng") is True


def test_catchment_unrelated_listing_still_filtered_out():
    listing = _listing(title="Sunny 1br", catchments=SchoolCatchments())
    assert _catchment_matches(listing, "lord byng") is False


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
async def test_unresolvable_neighborhood_skips_filter_not_drops_all(session):
    """When every requested name fails to resolve (typo, deprecated
    alias, unknown name in a saved query), the filter is skipped rather
    than dropping every listing — Codex review #97. The resolver
    silently drops unknown names; the post-filter must follow suit
    instead of turning an unresolvable filter into a hard zero-result
    query.
    """
    in_dunbar = _raw_at(1, lat=49.255, lon=-123.185)
    in_kits = _raw_at(2, lat=49.268, lon=-123.165)
    adapter = FakeAdapter(listings=[in_dunbar, in_kits])
    svc = AggregatorService(adapters=[adapter], session=session, cache_ttl_seconds=900)
    resp = await svc.search(
        SearchRequest(query=NormalizedQuery(neighborhoods=["Atlantis", "DunbarTypo"]))
    )
    await session.commit()
    # Both listings survive — the filter was skipped because nothing
    # resolved.
    assert {x.source_listing_id for x in resp.listings} == {"1", "2"}


class _StubScaffold(ScaffoldAdapterBase):
    """Concrete scaffold subclass that doesn't override `_extract`."""

    name: str = "stub_scaffold"
    base_url: str = "https://example.test"


class _StubScaffoldWithStubExtract(ScaffoldAdapterBase):
    """Mirrors the real-world livrent / zumper / rew shape: subclass
    overrides `_extract` with its own log-and-return-`[]` stub. The
    detector must still flag this as uncalibrated (Codex review
    catch — method-identity introspection missed this case)."""

    name: str = "stub_scaffold_with_extract"
    base_url: str = "https://example.test"

    def _extract(self, html: str, query: NormalizedQuery) -> list[RawListing]:
        return []


class _CalibratedScaffold(ScaffoldAdapterBase):
    """Scaffold subclass that has flipped the `is_extractor_calibrated`
    flag — the path a future PadMapper / Rentals.ca calibration takes."""

    name: str = "calibrated_scaffold"
    base_url: str = "https://example.test"
    is_extractor_calibrated: bool = True

    def _extract(self, html: str, query: NormalizedQuery) -> list[RawListing]:
        return []


def test_uncalibrated_scaffold_base_default_detected():
    """Subclass that doesn't override `_extract` is uncalibrated (#94)."""
    stub = _StubScaffold(user_agent="rentwise-test/0.1")
    assert _is_uncalibrated_scaffold(stub) is True


def test_uncalibrated_scaffold_with_stub_extract_detected():
    """Subclass that overrides `_extract` with a stub is *still* uncalibrated.
    Regression for the Codex review on #99 — the previous method-identity
    check missed every real scaffold (livrent / zumper / rew)."""
    stub = _StubScaffoldWithStubExtract(user_agent="rentwise-test/0.1")
    assert _is_uncalibrated_scaffold(stub) is True


def test_calibrated_scaffold_flag_lifts_warning():
    """Setting `is_extractor_calibrated=True` opts out of the warning."""
    cal = _CalibratedScaffold(user_agent="rentwise-test/0.1")
    assert _is_uncalibrated_scaffold(cal) is False


def test_non_scaffold_adapter_not_flagged():
    """A production adapter (FakeAdapter / Craigslist / etc.) isn't a scaffold.
    Default for adapters with no `is_extractor_calibrated` attribute is True
    — they were never stubs, so we never warn."""
    adapter = FakeAdapter(listings=[])
    assert _is_uncalibrated_scaffold(adapter) is False


def test_real_scaffold_classes_flagged():
    """The actual project scaffolds — livrent / zumper / rew — must
    be flagged. They each ship their own stub `_extract` so the old
    method-identity check missed all three."""
    from rentwise.adapters.livrent.adapter import LivRentAdapter
    from rentwise.adapters.rew.adapter import RewAdapter
    from rentwise.adapters.zumper.adapter import ZumperAdapter

    for cls in (LivRentAdapter, ZumperAdapter, RewAdapter):
        adapter = cls(user_agent="rentwise-test/0.1")
        assert _is_uncalibrated_scaffold(adapter) is True, f"{cls.__name__} should be flagged"


def test_non_scaffold_base_classes_flagged():
    """PadMapper / Rentals.ca aren't ScaffoldAdapterBase subclasses
    but still ship uncalibrated extractors — they declare the flag
    directly so the detector treats them like any other scaffold."""
    from rentwise.adapters.padmapper.adapter import PadMapperAdapter
    from rentwise.adapters.rentalsca.adapter import RentalsCaAdapter

    pad = PadMapperAdapter(user_agent="rentwise-test/0.1")
    assert _is_uncalibrated_scaffold(pad) is True
    rca = RentalsCaAdapter(user_agent="rentwise-test/0.1")
    assert _is_uncalibrated_scaffold(rca) is True


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
