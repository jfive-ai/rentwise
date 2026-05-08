"""End-to-end test: Phase 4 PR-A enrichment fires on /search.

Spins up the FastAPI app with:
  - a fake adapter yielding RawListings with real addresses but no lat/lon
  - a fake Geocoder injected via the get_geocoder dependency override

Asserts:
  - Listings come back with lat/lon populated and address_normalized set.
  - A second /search hits the cache (geocoder call_count does not grow).
"""

from __future__ import annotations

import concurrent.futures
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl

from rentwise.adapters.base import AdapterCapabilities
from rentwise.enrichment.geocode import GeocodeResult
from rentwise.models import NormalizedQuery, RawListing


class _FakeAdapter:
    """Minimal SourceAdapter for integration tests."""

    name = "fake_geo_source"
    base_url = "https://example.com"
    method = "api"
    rate_limit_per_second = 1.0
    capabilities: ClassVar[AdapterCapabilities] = {
        "supported_filters": {"bedrooms_min", "price_min", "price_max"},
    }

    def __init__(self, listings: list[RawListing]) -> None:
        self._listings = listings

    async def search(self, query: NormalizedQuery) -> AsyncIterator[RawListing]:
        for listing in self._listings:
            yield listing

    async def fetch_listing(self, listing_id: str) -> RawListing | None:
        for listing in self._listings:
            if listing.source_listing_id == listing_id:
                return listing
        return None

    async def health_check(self):
        from rentwise.models import AdapterHealth

        return AdapterHealth(name=self.name, status="ok")


class _FakeGeocoder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def geocode(self, query: str) -> GeocodeResult | None:
        self.calls.append(query)
        # Simple deterministic mapping — every query gets the same coords.
        return GeocodeResult(lat=49.2661, lon=-123.1525)


def _raw(idx: int, address: str, *, source: str = "fake_geo_source") -> RawListing:
    return RawListing(
        source=source,
        source_url=HttpUrl(f"https://example.com/{source}/listing/{idx}"),
        source_listing_id=str(idx),
        title=f"Listing {idx}",
        address=address,
        lat=None,
        lon=None,
        bedrooms=2.0,
        bathrooms=1.0,
        price_cad=2500 + idx * 100,
        pets_allowed=None,
        furnished=None,
        available_date=None,
        posted_at=datetime.now(UTC),
        photos=[],
        description_snippet=None,
        raw_metadata={},
    )


@pytest.fixture
def app_client(monkeypatch, tmp_sqlite_url):
    monkeypatch.setenv("DATABASE_URL", tmp_sqlite_url)

    from alembic.config import Config

    from alembic import command

    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", tmp_sqlite_url)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(command.upgrade, cfg, "head").result()

    from rentwise.storage import db as dbmod

    dbmod.get_engine.cache_clear()
    dbmod.get_sessionmaker.cache_clear()

    from rentwise.settings import settings

    settings.database_url = tmp_sqlite_url

    from rentwise.http.search import get_adapters, get_geocoder
    from rentwise.main import create_app

    fake_adapter = _FakeAdapter(
        [
            _raw(1, "1234 W 4th Ave, Vancouver, BC"),
            _raw(2, "350 W Georgia St, Vancouver, BC"),
        ]
    )
    fake_geocoder = _FakeGeocoder()

    app = create_app()
    app.dependency_overrides[get_adapters] = lambda: [fake_adapter]
    app.dependency_overrides[get_geocoder] = lambda: fake_geocoder

    with TestClient(app) as client:
        yield client, fake_geocoder


@pytest.mark.integration
def test_search_geocodes_listings(app_client) -> None:
    client, geocoder = app_client
    r = client.post("/search", json={"query": {"bedrooms_min": 1}, "limit": 50})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert body["cache_status"] == "miss"
    assert all(item["lat"] is not None for item in body["listings"])
    assert all(item["lon"] is not None for item in body["listings"])
    assert all(item["address_normalized"] for item in body["listings"])

    # First /search: each unique address triggers exactly one geocode call.
    assert len(geocoder.calls) == 2


@pytest.mark.integration
def test_second_search_uses_cache(app_client) -> None:
    client, geocoder = app_client

    client.post("/search", json={"query": {"bedrooms_min": 1}, "limit": 50})
    first_calls = len(geocoder.calls)

    # Different query → bypasses search cache → re-runs the adapter →
    # still hits enrichment, but the geocode cache is warm so no new
    # network calls.
    client.post(
        "/search",
        json={"query": {"bedrooms_min": 1, "price_max": 99999}, "limit": 50},
    )
    assert len(geocoder.calls) == first_calls


@pytest.fixture
def app_client_post_filter(monkeypatch, tmp_sqlite_url):
    """Variant of app_client whose geocoder dispatches per-address so we
    can place listings inside vs outside the synthetic Lord Byng polygon."""
    monkeypatch.setenv("DATABASE_URL", tmp_sqlite_url)

    from alembic.config import Config

    from alembic import command

    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", tmp_sqlite_url)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(command.upgrade, cfg, "head").result()

    from rentwise.storage import db as dbmod

    dbmod.get_engine.cache_clear()
    dbmod.get_sessionmaker.cache_clear()

    from rentwise.settings import settings

    settings.database_url = tmp_sqlite_url

    from rentwise.http.search import get_adapters, get_geocoder
    from rentwise.main import create_app

    # Two listings with parseable Vancouver addresses. The geocoder
    # dispatches by street so one lands in the synthetic Lord Byng
    # polygon and one lands outside it.
    fake_adapter = _FakeAdapter(
        [
            _raw(101, "1234 W 8th Ave, Vancouver, BC"),
            _raw(102, "5500 E 49th Ave, Vancouver, BC"),
        ]
    )

    class _DispatchingGeocoder:
        def __init__(self):
            self.calls = []

        async def geocode(self, query: str):
            self.calls.append(query)
            if "8th avenue" in query.lower():
                return GeocodeResult(lat=49.275, lon=-123.180)
            return GeocodeResult(lat=49.230, lon=-123.080)

    geo = _DispatchingGeocoder()

    app = create_app()
    app.dependency_overrides[get_adapters] = lambda: [fake_adapter]
    app.dependency_overrides[get_geocoder] = lambda: geo

    with TestClient(app) as client:
        yield client, geo


@pytest.mark.integration
def test_school_catchment_post_filter_drops_outside_listings(app_client_post_filter) -> None:
    client, _geo = app_client_post_filter
    r = client.post("/search", json={"query": {"school_catchment": "Lord Byng"}, "limit": 50})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["listings"][0]["source_listing_id"] == "101"
    assert body["listings"][0]["school_catchments"]["secondary"] == "Lord Byng"
    assert "school_catchment" not in body["unsupported_filters"]


@pytest.mark.integration
def test_transit_max_walk_post_filter(app_client_post_filter) -> None:
    """Both listings get a nearest_transit (synthetic stops cover the city);
    a max-walk filter that only the inside-Byng coords satisfy proves the
    aggregator drops the other one."""
    client, _geo = app_client_post_filter
    # Inside-Byng (49.275, -123.180) is ~5 km from Broadway-City Hall but
    # closer to W 4th @ MacDonald (10020 at 49.268, -123.174). The outside
    # listing (49.230, -123.080) is closest to Joyce-Collingwood (49.238,
    # -123.032) — much further from any other stop. Cap walk at 4 minutes
    # to drop the latter.
    r = client.post("/search", json={"query": {"transit_max_walk_minutes": 4}, "limit": 50})
    assert r.status_code == 200, r.text
    body = r.json()
    # At least the obviously-far listing must be dropped.
    ids = {lst["source_listing_id"] for lst in body["listings"]}
    assert "102" not in ids
    assert "transit_max_walk_minutes" not in body["unsupported_filters"]


# ---------------------------------------------------------------------------
# Cross-source dedup (Phase 4 PR-C)
# ---------------------------------------------------------------------------


class _SecondFakeAdapter(_FakeAdapter):
    """Same as _FakeAdapter but advertised under a different source name
    so cross-source merging is exercised."""

    name = "fake_geo_source_b"


@pytest.fixture
def app_client_dedup(monkeypatch, tmp_sqlite_url):
    """Two adapters yielding the same building under different
    (source, source_listing_id) pairs — dedup should collapse them."""
    monkeypatch.setenv("DATABASE_URL", tmp_sqlite_url)

    from alembic.config import Config

    from alembic import command

    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", tmp_sqlite_url)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(command.upgrade, cfg, "head").result()

    from rentwise.storage import db as dbmod

    dbmod.get_engine.cache_clear()
    dbmod.get_sessionmaker.cache_clear()

    from rentwise.settings import settings

    settings.database_url = tmp_sqlite_url

    from rentwise.http.search import (
        get_adapters,
        get_geocoder,
        get_photo_hasher,
    )
    from rentwise.main import create_app

    # Same address, similar price, identical bedrooms — should merge.
    # Each adapter yields its listing under its own `source` so the
    # (source, source_listing_id) unique constraint doesn't collapse
    # them into one row before dedup gets a look in.
    adapter_a = _FakeAdapter([_raw(1, "1234 W 8th Ave, Vancouver, BC", source="fake_geo_source")])
    adapter_b = _SecondFakeAdapter(
        [_raw(1, "1234 W 8th Ave, Vancouver, BC", source="fake_geo_source_b")]
    )

    class _OneCoordsGeocoder:
        async def geocode(self, query: str):
            return GeocodeResult(lat=49.275, lon=-123.180)

    class _NoOpHasher:
        async def hash_url(self, url: str) -> str | None:
            return None

    app = create_app()
    app.dependency_overrides[get_adapters] = lambda: [adapter_a, adapter_b]
    app.dependency_overrides[get_geocoder] = lambda: _OneCoordsGeocoder()
    app.dependency_overrides[get_photo_hasher] = lambda: _NoOpHasher()

    with TestClient(app) as client:
        yield client


@pytest.mark.integration
def test_cross_source_listings_collapse_to_one_canonical(app_client_dedup) -> None:
    """Two adapters yielding the same building → two listings, one canonical_id."""
    client = app_client_dedup
    # First call ingests both. Both have address+price+bedrooms in common,
    # so the second one merges into the first under the dedup threshold.
    r = client.post("/search", json={"query": {"bedrooms_min": 1}, "limit": 50})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2  # both listings come back
    canonical_ids = {item["canonical_id"] for item in body["listings"]}
    assert len(canonical_ids) == 1, (
        f"expected one canonical_id across the two cross-source rows, got {canonical_ids}"
    )
    sources = {item["source"] for item in body["listings"]}
    assert sources == {"fake_geo_source", "fake_geo_source_b"}
