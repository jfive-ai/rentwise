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
async def test_sort_title_and_source_and_bedrooms_directions(session):
    adapter = FakeAdapter(
        listings=[
            RawListing(
                source="zumper",
                source_url=HttpUrl("https://x/c"),
                source_listing_id="c",
                title="Cozy condo",
                bedrooms=1,
                price_cad=2000,
                posted_at=datetime.now(UTC),
            ),
            RawListing(
                source="craigslist",
                source_url=HttpUrl("https://x/a"),
                source_listing_id="a",
                title="Apple loft",
                bedrooms=3,
                price_cad=2500,
                posted_at=datetime.now(UTC),
            ),
            RawListing(
                source="padmapper",
                source_url=HttpUrl("https://x/b"),
                source_listing_id="b",
                title="Bright suite",
                bedrooms=2,
                price_cad=2200,
                posted_at=datetime.now(UTC),
            ),
        ]
    )
    svc = AggregatorService(adapters=[adapter], session=session, cache_ttl_seconds=900)

    resp = await svc.search(SearchRequest(query=NormalizedQuery(), sort=SortOrder.TITLE_ASC))
    assert [x.title for x in resp.listings] == ["Apple loft", "Bright suite", "Cozy condo"]

    resp = await svc.search(
        SearchRequest(query=NormalizedQuery(), sort=SortOrder.TITLE_DESC, force_refresh=True)
    )
    assert [x.title for x in resp.listings] == ["Cozy condo", "Bright suite", "Apple loft"]

    resp = await svc.search(
        SearchRequest(query=NormalizedQuery(), sort=SortOrder.SOURCE_ASC, force_refresh=True)
    )
    assert [x.source for x in resp.listings] == ["craigslist", "padmapper", "zumper"]

    resp = await svc.search(
        SearchRequest(query=NormalizedQuery(), sort=SortOrder.SOURCE_DESC, force_refresh=True)
    )
    assert [x.source for x in resp.listings] == ["zumper", "padmapper", "craigslist"]

    resp = await svc.search(
        SearchRequest(query=NormalizedQuery(), sort=SortOrder.BEDROOMS_ASC, force_refresh=True)
    )
    assert [x.bedrooms for x in resp.listings] == [1, 2, 3]

    resp = await svc.search(
        SearchRequest(query=NormalizedQuery(), sort=SortOrder.BEDROOMS_DESC, force_refresh=True)
    )
    assert [x.bedrooms for x in resp.listings] == [3, 2, 1]


@pytest.mark.asyncio
async def test_legacy_bedrooms_alias_sorts_descending(session):
    """The legacy ?sort=bedrooms value (pre asc/desc split) must keep
    sorting descending so older shared URLs don't break."""
    adapter = FakeAdapter(
        listings=[
            RawListing(
                source="craigslist",
                source_url=HttpUrl("https://x/1"),
                source_listing_id="1",
                title="one",
                bedrooms=1,
                posted_at=datetime.now(UTC),
            ),
            RawListing(
                source="craigslist",
                source_url=HttpUrl("https://x/3"),
                source_listing_id="3",
                title="three",
                bedrooms=3,
                posted_at=datetime.now(UTC),
            ),
        ]
    )
    svc = AggregatorService(adapters=[adapter], session=session, cache_ttl_seconds=900)
    resp = await svc.search(SearchRequest(query=NormalizedQuery(), sort=SortOrder.BEDROOMS))
    assert [x.bedrooms for x in resp.listings] == [3, 1]


@pytest.mark.asyncio
async def test_match_score_applied_on_cache_hit(session):
    """Codex P1 on PR #127: cached responses must include match_score so
    MATCH_DESC sort works and the badge appears on repeat searches."""
    adapter = FakeAdapter(
        listings=[
            RawListing(
                source="craigslist",
                source_url=HttpUrl("https://x/1"),
                source_listing_id="1",
                title="A",
                bedrooms=2,
                price_cad=2500,
                posted_at=datetime.now(UTC),
            ),
        ]
    )
    svc = AggregatorService(adapters=[adapter], session=session, cache_ttl_seconds=900)
    req = SearchRequest(query=NormalizedQuery(price_max=3000), sort=SortOrder.MATCH_DESC)
    miss = await svc.search(req)
    await session.commit()
    assert miss.cache_status == "miss"
    assert miss.listings[0].match_score is not None
    miss_score = miss.listings[0].match_score
    # Second identical request hits the cache; scoring must still run.
    hit = await svc.search(req)
    assert hit.cache_status == "fresh"
    assert hit.listings[0].match_score is not None
    assert hit.listings[0].match_score == miss_score
    assert hit.listings[0].match_explanation


@pytest.mark.asyncio
async def test_match_score_attached_to_every_listing(session):
    """Issue #119: every listing in the response carries a 0-100 score."""
    adapter = FakeAdapter(
        listings=[
            RawListing(
                source="craigslist",
                source_url=HttpUrl("https://x/1"),
                source_listing_id="1",
                title="cheap 2BR",
                bedrooms=2,
                price_cad=2500,
                posted_at=datetime.now(UTC),
            ),
            RawListing(
                source="craigslist",
                source_url=HttpUrl("https://x/2"),
                source_listing_id="2",
                title="expensive 2BR",
                bedrooms=2,
                price_cad=4500,
                posted_at=datetime.now(UTC),
            ),
        ]
    )
    svc = AggregatorService(adapters=[adapter], session=session, cache_ttl_seconds=900)
    resp = await svc.search(SearchRequest(query=NormalizedQuery(price_max=3000)))
    for r in resp.listings:
        assert r.match_score is not None
        assert 0 <= r.match_score <= 100


@pytest.mark.asyncio
async def test_match_desc_sorts_best_fit_first(session):
    """Issue #119: MATCH_DESC sort puts in-budget listings above out-of-budget."""
    adapter = FakeAdapter(
        listings=[
            RawListing(
                source="craigslist",
                source_url=HttpUrl("https://x/over"),
                source_listing_id="over",
                title="over budget",
                bedrooms=2,
                price_cad=4500,
                posted_at=datetime.now(UTC),
                address="A St",
                description_snippet="d",
            ),
            RawListing(
                source="craigslist",
                source_url=HttpUrl("https://x/inb"),
                source_listing_id="inb",
                title="in budget",
                bedrooms=2,
                price_cad=2500,
                posted_at=datetime.now(UTC),
                address="B St",
                description_snippet="d",
            ),
        ]
    )
    svc = AggregatorService(adapters=[adapter], session=session, cache_ttl_seconds=900)
    resp = await svc.search(
        SearchRequest(query=NormalizedQuery(price_max=3000), sort=SortOrder.MATCH_DESC)
    )
    assert [r.source_listing_id for r in resp.listings] == ["inb", "over"]


@pytest.mark.asyncio
async def test_per_adapter_commit_releases_write_lock(session, monkeypatch):
    """#109 follow-up: each adapter's writes must be committed before the
    next adapter starts, otherwise a single /search holds the SQLite
    write lock for its entire 30-60 s lifetime and any concurrent
    request 503s. We can't measure the lock directly here, but we
    can prove the aggregator commits inside the adapter loop by
    counting commits during search.
    """
    a = FakeAdapter(listings=[_raw(1)])
    b = FakeAdapter(listings=[_raw(2)])
    b.name = "rentalsca"  # type: ignore[misc]
    svc = AggregatorService(adapters=[a, b], session=session, cache_ttl_seconds=900)

    real_commit = session.commit
    commit_count = 0

    async def counting_commit():
        nonlocal commit_count
        commit_count += 1
        await real_commit()

    monkeypatch.setattr(session, "commit", counting_commit)

    await svc.search(SearchRequest(query=NormalizedQuery(bedrooms_min=1)))

    # Two successful adapters → at least two commits inside the loop.
    # (The wrapper at http/search.py adds one more outside the
    # aggregator; that one isn't exercised by this test.)
    assert commit_count >= 2, (
        f"expected per-adapter commits to release the SQLite write lock, "
        f"got {commit_count} commits across 2 adapters"
    )


@pytest.mark.asyncio
async def test_failing_adapter_does_not_block_subsequent_adapters(session):
    """#109 follow-up: a failed adapter must not prevent later adapters
    from running. The original bug was that an OperationalError
    mid-flush poisoned the session and the aggregator's health write
    re-raised PendingRollbackError, escaping to the 503 wrapper.
    """
    failing = FakeAdapter(listings=[], should_raise=RuntimeError("boom"))
    succeeding = FakeAdapter(listings=[_raw(99)])
    succeeding.name = "rentalsca"  # type: ignore[misc]

    svc = AggregatorService(adapters=[failing, succeeding], session=session, cache_ttl_seconds=900)

    resp = await svc.search(SearchRequest(query=NormalizedQuery(bedrooms_min=1)))

    assert resp.source_health["craigslist"].status == "degraded"
    assert resp.source_health["rentalsca"].status == "ok"
    assert any(str(x.source_listing_id) == "99" for x in resp.listings)


@pytest.mark.asyncio
async def test_partial_adapter_failure_preserves_already_flushed_listings(session):
    """Codex review on #111 (P1): an adapter that yields some listings
    and then raises a *non-DB* error (parsing, network) must keep the
    rows it successfully flushed. Previously the unconditional
    `session.rollback()` discarded the DB rows while their UUIDs
    stayed in `all_listings`, so the search cache referenced rows
    that didn't exist and subsequent cache hits returned fewer
    results than `total_count`.

    A second succeeding adapter is included so `any_succeeded`
    becomes True and the cache write happens — that's where the
    original bug manifested.
    """
    from rentwise.storage.repositories import ListingRepo

    class PartiallyFailingAdapter:
        name = "padmapper"
        base_url = "https://padmapper.com"
        method = "browser"
        rate_limit_per_second = 1.0
        capabilities: ClassVar[AdapterCapabilities] = {
            "supported_filters": {"bedrooms_min", "price_max"}
        }

        async def search(self, query: NormalizedQuery) -> AsyncIterator[RawListing]:
            for src_id in ("p1", "p2"):
                yield RawListing(
                    source="padmapper",
                    source_url=HttpUrl(f"https://padmapper.com/{src_id}"),
                    source_listing_id=src_id,
                    title=f"$2000 / 1br - {src_id}",
                    bedrooms=1.0,
                    price_cad=2000,
                    posted_at=datetime.now(UTC),
                )
            raise RuntimeError("network failure mid-iteration")

        async def fetch_listing(self, listing_id: str):
            return None

        async def health_check(self) -> AdapterHealth:
            return AdapterHealth(name=self.name, status="ok")

    succeeding = FakeAdapter(listings=[_raw(99)])
    svc = AggregatorService(
        adapters=[PartiallyFailingAdapter(), succeeding],
        session=session,
        cache_ttl_seconds=900,
    )
    resp = await svc.search(SearchRequest(query=NormalizedQuery(bedrooms_min=1)))

    # All three listings survived: padmapper's partial p1+p2 plus
    # craigslist's 99.
    ids = {str(x.source_listing_id) for x in resp.listings}
    assert ids == {"p1", "p2", "99"}, f"expected partial listings to survive, got {ids}"
    assert resp.source_health["padmapper"].status == "degraded"
    assert resp.source_health["craigslist"].status == "ok"

    # And they're actually in the DB — not phantoms in `all_listings`
    # that would dangle in the search cache.
    repo = ListingRepo(session)
    assert await repo.get_by_source("padmapper", "p1") is not None
    assert await repo.get_by_source("padmapper", "p2") is not None
    assert await repo.get_by_source("craigslist", "99") is not None


@pytest.mark.asyncio
async def test_db_poisoning_failure_drops_in_memory_listings(session, monkeypatch):
    """Codex review on #111 (P1) flip side: when the per-adapter
    `commit` fails (the session is genuinely poisoned by a DB error),
    rollback the session AND drop the in-memory listings back to the
    pre-adapter snapshot. Otherwise dangling UUIDs end up in the
    search cache and subsequent cache hits return fewer rows than
    `total_count` claims.
    """
    adapter = FakeAdapter(listings=[_raw(1), _raw(2)])
    svc = AggregatorService(adapters=[adapter], session=session, cache_ttl_seconds=900)

    # Force the per-adapter `commit` (called inside the aggregator
    # loop) to fail exactly once, simulating a session poisoned by a
    # DB-layer error mid-flush. Subsequent commits (the health write
    # and the final cache write) must still succeed.
    real_commit = session.commit
    fail_next: list[bool] = [True]

    async def flaky_commit():
        if fail_next[0]:
            fail_next[0] = False
            await real_commit()  # actually commit so DB state is consistent
            raise RuntimeError("simulated session poisoning")
        await real_commit()

    monkeypatch.setattr(session, "commit", flaky_commit)

    resp = await svc.search(SearchRequest(query=NormalizedQuery(bedrooms_min=1)))

    # The adapter's listings were dropped from the in-memory list
    # because we treated the (simulated) commit failure as
    # poisoning. The response should have zero listings even
    # though the adapter yielded two.
    assert resp.listings == [], (
        f"in-memory listings must be dropped on commit failure to avoid "
        f"dangling UUIDs in the search cache, got {len(resp.listings)}"
    )
    assert resp.source_health["craigslist"].status == "degraded"


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
    """The remaining project scaffolds — zumper / rew — must still be
    flagged. liv.rent was calibrated against live HTML in #105 and
    should NOT be flagged any more; we keep it in the test as a
    negative case so a future regression on `is_extractor_calibrated`
    fails loudly."""
    from rentwise.adapters.livrent.adapter import LivRentAdapter
    from rentwise.adapters.rew.adapter import RewAdapter
    from rentwise.adapters.zumper.adapter import ZumperAdapter

    for cls in (ZumperAdapter, RewAdapter):
        adapter = cls(user_agent="rentwise-test/0.1")
        assert _is_uncalibrated_scaffold(adapter) is True, f"{cls.__name__} should be flagged"

    livrent = LivRentAdapter(user_agent="rentwise-test/0.1")
    assert _is_uncalibrated_scaffold(livrent) is False, (
        "liv.rent extractor is calibrated as of #105 — flag should be False"
    )


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
