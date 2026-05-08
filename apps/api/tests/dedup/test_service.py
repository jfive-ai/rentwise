"""DedupService tests — uses the real ListingRepo on an in-memory DB."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import HttpUrl

from rentwise.dedup.service import DedupConfig, DedupService
from rentwise.models import NormalizedListing, SchoolCatchments
from rentwise.storage.repositories import ListingRepo


def _listing(
    *,
    source: str = "craigslist",
    source_listing_id: str = "1",
    address_normalized: str | None = "1234 west 4th avenue vancouver bc",
    price_cad: int | None = 2800,
    bedrooms: float | None = 2.0,
    phash: str | None = None,
    canonical_id: UUID | None = None,
) -> NormalizedListing:
    nid = uuid4()
    now = datetime.now(UTC)
    return NormalizedListing(
        id=nid,
        canonical_id=canonical_id or nid,
        source=source,
        source_url=HttpUrl(f"https://example.com/{source}/{source_listing_id}"),
        source_listing_id=source_listing_id,
        title="Bright 2BR",
        address="1234 W 4th Ave, Vancouver, BC",
        address_normalized=address_normalized,
        lat=49.275,
        lon=-123.18,
        bedrooms=bedrooms,
        bathrooms=None,
        price_cad=price_cad,
        pets_allowed=None,
        furnished=None,
        available_date=None,
        posted_at=now,
        last_seen_at=now,
        photos=[],
        description_snippet=None,
        school_catchments=SchoolCatchments(),
        phash=phash,
        raw_metadata={},
    )


@pytest.mark.asyncio
async def test_dedup_disabled_is_noop(session) -> None:
    svc = DedupService(session, config=DedupConfig(enabled=False))
    listing = _listing()
    out = await svc.assign_canonical(listing)
    assert out is listing


@pytest.mark.asyncio
async def test_dedup_skips_listing_without_address(session) -> None:
    svc = DedupService(session)
    listing = _listing(address_normalized=None)
    out = await svc.assign_canonical(listing)
    assert out.canonical_id == listing.canonical_id


@pytest.mark.asyncio
async def test_dedup_keeps_self_canonical_with_no_candidates(session) -> None:
    svc = DedupService(session)
    listing = _listing()
    out = await svc.assign_canonical(listing)
    assert out.canonical_id == listing.canonical_id


@pytest.mark.asyncio
async def test_dedup_assigns_existing_canonical_when_above_threshold(session) -> None:
    """Pre-seed a listing with the same address+price; new listing should
    inherit its canonical_id."""
    repo = ListingRepo(session)
    seed = _listing(source="rentals_ca", source_listing_id="A1", price_cad=2800, bedrooms=2.0)
    saved = await repo.upsert(seed)

    svc = DedupService(session)
    incoming = _listing(source="craigslist", source_listing_id="C9", price_cad=2810, bedrooms=2.0)
    out = await svc.assign_canonical(incoming)
    assert out.canonical_id == saved.canonical_id
    assert out.canonical_id != incoming.canonical_id


@pytest.mark.asyncio
async def test_dedup_does_not_merge_when_below_threshold(session) -> None:
    """Same address but wildly different price → score below threshold."""
    repo = ListingRepo(session)
    seed = _listing(source="rentals_ca", source_listing_id="A1", price_cad=2800, bedrooms=2.0)
    await repo.upsert(seed)

    svc = DedupService(session)
    # Different bedrooms + far-off price → score = 0.5 (address only).
    incoming = _listing(source="craigslist", source_listing_id="C9", price_cad=4500, bedrooms=4.0)
    out = await svc.assign_canonical(incoming)
    assert out.canonical_id == incoming.canonical_id  # unchanged


@pytest.mark.asyncio
async def test_dedup_excludes_self_match(session) -> None:
    """A listing with the same (source, source_listing_id) as one in the DB
    must not be considered its own match."""
    repo = ListingRepo(session)
    seed = _listing(source="craigslist", source_listing_id="C9")
    await repo.upsert(seed)

    svc = DedupService(session)
    # Same source + id → exclusion kicks in. The listing keeps its own
    # canonical_id (no other candidates exist).
    incoming = _listing(source="craigslist", source_listing_id="C9")
    out = await svc.assign_canonical(incoming)
    assert out.canonical_id == incoming.canonical_id


@pytest.mark.asyncio
async def test_dedup_picks_best_among_multiple_candidates(session) -> None:
    """Two pre-seeded candidates; the one with the higher confidence wins."""
    repo = ListingRepo(session)
    addr = "1234 west 4th avenue vancouver bc"
    weak = _listing(
        source="rentals_ca",
        source_listing_id="A1",
        address_normalized=addr,
        price_cad=4500,  # outside tolerance
        bedrooms=4.0,  # mismatched
    )
    strong = _listing(
        source="padmapper",
        source_listing_id="P9",
        address_normalized=addr,
        price_cad=2810,  # within tolerance
        bedrooms=2.0,  # match
    )
    await repo.upsert(weak)
    saved_strong = await repo.upsert(strong)

    svc = DedupService(session)
    incoming = _listing(
        source="craigslist",
        source_listing_id="C9",
        price_cad=2800,
        bedrooms=2.0,
    )
    out = await svc.assign_canonical(incoming)
    assert out.canonical_id == saved_strong.canonical_id
