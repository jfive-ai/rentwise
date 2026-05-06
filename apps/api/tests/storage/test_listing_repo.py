"""Tests for ListingRepo."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import HttpUrl

from rentwise.models import NormalizedListing, SchoolCatchments
from rentwise.storage.repositories import ListingRepo


def _make_listing(**overrides) -> NormalizedListing:
    now = datetime.now(UTC)
    base = dict(
        id=uuid4(),
        canonical_id=uuid4(),
        source="craigslist",
        source_url=HttpUrl("https://example.com/x"),
        source_listing_id="abc",
        title="Bright 2BR in Kits",
        address=None,
        address_normalized=None,
        lat=49.27,
        lon=-123.16,
        bedrooms=2.0,
        bathrooms=None,
        price_cad=2800,
        pets_allowed=None,
        furnished=None,
        available_date=None,
        posted_at=now,
        last_seen_at=now,
        photos=[],
        description_snippet="Snippet text",
    )
    base.update(overrides)
    return NormalizedListing(**base)


@pytest.mark.asyncio
async def test_upsert_inserts_new_listing(session):
    repo = ListingRepo(session)
    listing = _make_listing()
    saved = await repo.upsert(listing)
    await session.commit()
    fetched = await repo.get_by_source(listing.source, listing.source_listing_id)
    assert fetched is not None
    assert str(fetched.id) == str(saved.id)
    assert fetched.title == listing.title


@pytest.mark.asyncio
async def test_upsert_preserves_id_on_repeat(session):
    """Re-ingesting same (source, source_listing_id) keeps the original id and updates last_seen_at."""
    repo = ListingRepo(session)
    listing = _make_listing()
    first = await repo.upsert(listing)
    await session.commit()

    later = listing.model_copy(update={"title": "Updated title"})
    second = await repo.upsert(later)
    await session.commit()

    assert str(first.id) == str(second.id)
    fetched = await repo.get_by_source(listing.source, listing.source_listing_id)
    assert fetched.title == "Updated title"


@pytest.mark.asyncio
async def test_school_catchments_roundtrip(session):
    repo = ListingRepo(session)
    listing = _make_listing(
        school_catchments=SchoolCatchments(
            elementary="Lord Tennyson Elementary",
            secondary="Kitsilano Secondary",
        )
    )
    await repo.upsert(listing)
    await session.commit()
    fetched = await repo.get_by_source(listing.source, listing.source_listing_id)
    assert fetched.school_catchments.elementary == "Lord Tennyson Elementary"
    assert fetched.school_catchments.middle is None
    assert fetched.school_catchments.secondary == "Kitsilano Secondary"


@pytest.mark.asyncio
async def test_list_by_ids_preserves_order(session):
    repo = ListingRepo(session)
    a = await repo.upsert(_make_listing(source_listing_id="a"))
    b = await repo.upsert(_make_listing(source_listing_id="b"))
    c = await repo.upsert(_make_listing(source_listing_id="c"))
    await session.commit()

    ordered = await repo.list_by_ids([str(c.id), str(a.id), str(b.id)])
    assert [str(x.id) for x in ordered] == [str(c.id), str(a.id), str(b.id)]
