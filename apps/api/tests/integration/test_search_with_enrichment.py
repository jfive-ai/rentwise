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


def _raw(idx: int, address: str) -> RawListing:
    return RawListing(
        source="fake_geo_source",
        source_url=HttpUrl(f"https://example.com/listing/{idx}"),
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
