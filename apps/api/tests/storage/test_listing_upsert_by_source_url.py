"""Tests for ListingRepo.upsert_by_source_url — null-skip + detail-wins merge."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import HttpUrl

from rentwise.storage.repositories import ListingRepo


def _fields(**overrides) -> dict:
    base = {
        "source_url": HttpUrl("https://rentals.ca/listing/abc"),
        "title": "Bright 2BR",
        "price_cad": 2800,
        "bedrooms": 2.0,
        "bathrooms": None,
        "neighborhood": "Kitsilano",
        "posted_at": None,
        "photos": [],
        "description_snippet": None,
        "thumbnail_url": HttpUrl("https://rentals.ca/img/abc.jpg"),
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_upsert_inserts_new_row_with_capture_method_and_first_seen(session):
    repo = ListingRepo(session)
    captured_at = datetime.now(UTC)
    saved = await repo.upsert_by_source_url(
        source="rentals_ca",
        source_listing_id="abc",
        fields=_fields(),
        capture_method="extension",
        page_type="search_results",
        captured_at=captured_at,
    )
    await session.commit()

    fetched = await repo.get_by_source("rentals_ca", "abc")
    assert fetched is not None
    assert fetched.title == "Bright 2BR"
    assert fetched.price_cad == 2800
    assert str(saved.id) == str(fetched.id)
    # Search-results capture seeds photos from thumbnail_url
    assert [str(p) for p in fetched.photos] == ["https://rentals.ca/img/abc.jpg"]


@pytest.mark.asyncio
async def test_upsert_null_field_does_not_overwrite_existing(session):
    repo = ListingRepo(session)
    t0 = datetime.now(UTC)

    await repo.upsert_by_source_url(
        source="rentals_ca",
        source_listing_id="abc",
        fields=_fields(description_snippet="Sunny west-facing 2BR"),
        capture_method="extension",
        page_type="listing_detail",
        captured_at=t0,
    )
    await session.commit()

    # Search-results capture without snippet must NOT clobber it
    await repo.upsert_by_source_url(
        source="rentals_ca",
        source_listing_id="abc",
        fields=_fields(description_snippet=None, price_cad=2900),
        capture_method="extension",
        page_type="search_results",
        captured_at=t0,
    )
    await session.commit()

    fetched = await repo.get_by_source("rentals_ca", "abc")
    assert fetched.description_snippet == "Sunny west-facing 2BR"
    assert fetched.price_cad == 2900  # non-null override is allowed


@pytest.mark.asyncio
async def test_search_results_capture_does_not_replace_detail_photos(session):
    repo = ListingRepo(session)
    t0 = datetime.now(UTC)

    detail_photos = [
        HttpUrl("https://rentals.ca/img/abc-1.jpg"),
        HttpUrl("https://rentals.ca/img/abc-2.jpg"),
    ]
    await repo.upsert_by_source_url(
        source="rentals_ca",
        source_listing_id="abc",
        fields=_fields(photos=detail_photos, thumbnail_url=None),
        capture_method="extension",
        page_type="listing_detail",
        captured_at=t0,
    )
    await session.commit()

    # Subsequent search-results capture would otherwise downgrade to [thumbnail]
    await repo.upsert_by_source_url(
        source="rentals_ca",
        source_listing_id="abc",
        fields=_fields(
            photos=[],
            thumbnail_url=HttpUrl("https://rentals.ca/img/abc-thumb.jpg"),
        ),
        capture_method="extension",
        page_type="search_results",
        captured_at=t0,
    )
    await session.commit()

    fetched = await repo.get_by_source("rentals_ca", "abc")
    assert len(fetched.photos) == 2  # detail's photos preserved


@pytest.mark.asyncio
async def test_upsert_advances_last_seen_at(session):
    repo = ListingRepo(session)
    t0 = datetime(2026, 5, 7, 10, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 5, 7, 11, 0, 0, tzinfo=UTC)

    await repo.upsert_by_source_url(
        source="rentals_ca",
        source_listing_id="abc",
        fields=_fields(),
        capture_method="extension",
        page_type="listing_detail",
        captured_at=t0,
    )
    await session.commit()

    await repo.upsert_by_source_url(
        source="rentals_ca",
        source_listing_id="abc",
        fields=_fields(),
        capture_method="extension",
        page_type="listing_detail",
        captured_at=t1,
    )
    await session.commit()

    fetched = await repo.get_by_source("rentals_ca", "abc")
    assert fetched.last_seen_at == t1
