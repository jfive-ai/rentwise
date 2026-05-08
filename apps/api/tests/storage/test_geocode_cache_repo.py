"""Tests for GeocodeCacheRepo: hits, misses, negative caching, staleness."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from rentwise.storage.repositories import GeocodeCacheEntry, GeocodeCacheRepo


def _entry(
    address_key: str = "1234 west 4th avenue vancouver bc",
    *,
    lat: float | None = 49.2661,
    lon: float | None = -123.1525,
    fetched_at: str | None = None,
    stale_after: str | None = None,
) -> GeocodeCacheEntry:
    now = datetime.now(UTC)
    return GeocodeCacheEntry(
        address_key=address_key,
        lat=lat,
        lon=lon,
        provider="nominatim",
        fetched_at=fetched_at or now.isoformat(),
        stale_after=stale_after or (now + timedelta(days=30)).isoformat(),
    )


@pytest.mark.asyncio
async def test_round_trip_insert_then_get(session):
    repo = GeocodeCacheRepo(session)
    entry = _entry()
    await repo.upsert(entry)
    fetched = await repo.get(entry.address_key)
    assert fetched is not None
    assert fetched.lat == entry.lat
    assert fetched.lon == entry.lon
    assert fetched.provider == "nominatim"


@pytest.mark.asyncio
async def test_get_returns_none_for_unknown_key(session):
    repo = GeocodeCacheRepo(session)
    assert await repo.get("nonexistent address") is None


@pytest.mark.asyncio
async def test_negative_result_is_cached(session):
    """A row with lat/lon = None still represents a cache hit — the geocoder
    confirmed there's no resolution, so we must not re-query."""
    repo = GeocodeCacheRepo(session)
    miss = _entry(address_key="garbage 99999 zzz", lat=None, lon=None)
    await repo.upsert(miss)
    fetched = await repo.get(miss.address_key)
    assert fetched is not None
    assert fetched.lat is None
    assert fetched.lon is None


@pytest.mark.asyncio
async def test_upsert_overwrites_existing(session):
    repo = GeocodeCacheRepo(session)
    initial = _entry(lat=49.0, lon=-123.0)
    await repo.upsert(initial)
    updated = _entry(lat=49.5, lon=-123.5)
    await repo.upsert(updated)
    fetched = await repo.get(initial.address_key)
    assert fetched is not None
    assert fetched.lat == 49.5
    assert fetched.lon == -123.5


def test_is_stale_true_for_past_cutoff():
    now = datetime.now(UTC)
    past = now - timedelta(seconds=1)
    entry = _entry(stale_after=past.isoformat())
    assert GeocodeCacheRepo.is_stale(entry, now=now) is True


def test_is_stale_false_for_future_cutoff():
    now = datetime.now(UTC)
    future = now + timedelta(days=1)
    entry = _entry(stale_after=future.isoformat())
    assert GeocodeCacheRepo.is_stale(entry, now=now) is False


def test_is_stale_handles_unparseable_cutoff():
    entry = _entry(stale_after="not a date")
    assert GeocodeCacheRepo.is_stale(entry) is True
