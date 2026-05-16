"""Tests for the quality / scam signal flags (issue #120).

One test per flag, plus a couple of integration cases that pin the
"clean listing yields no flags" and "flags are stable across runs"
contracts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import HttpUrl

from rentwise.models import NormalizedListing
from rentwise.quality.flags import (
    QualityFlag,
    build_context,
    compute_flags,
)


def _listing(
    *,
    id_: str | None = None,
    canonical: str | None = None,
    source: str = "craigslist",
    price: int | None = 2500,
    bedrooms: float | None = 2,
    address: str | None = "100 Test St",
    photos: bool = True,
    snippet: str | None = "Great place near transit",
    phash: str | None = None,
    raw_metadata: dict | None = None,
) -> NormalizedListing:
    lid = id_ or str(uuid4())
    cid = canonical or lid
    now = datetime.now(UTC)
    return NormalizedListing(
        id=lid,
        canonical_id=cid,
        source=source,
        source_url=HttpUrl(f"https://example.com/{lid}"),
        source_listing_id=lid,
        title=f"listing {lid}",
        address=address,
        address_normalized=None,
        lat=49.27,
        lon=-123.16,
        bedrooms=bedrooms,
        bathrooms=1,
        price_cad=price,
        pets_allowed=None,
        furnished=None,
        available_date=None,
        posted_at=now,
        last_seen_at=now,
        photos=[HttpUrl("https://example.com/p.jpg")] if photos else [],
        description_snippet=snippet,
        phash=phash,
        raw_metadata=raw_metadata or {},
    )


def test_clean_listing_has_no_flags() -> None:
    pool = [_listing() for _ in range(5)]
    ctx = build_context(pool)
    assert compute_flags(pool[0], ctx) == []


def test_missing_essentials_requires_address_missing() -> None:
    """Photos OR snippet missing alone — common on legit listings — doesn't fire."""
    listing = _listing(address="100 Real Ave", photos=False, snippet=None)
    ctx = build_context([listing])
    assert QualityFlag.MISSING_ESSENTIALS not in compute_flags(listing, ctx)


def test_missing_essentials_fires_when_address_and_photos_missing() -> None:
    listing = _listing(address=None, photos=False, snippet="some text")
    ctx = build_context([listing])
    assert QualityFlag.MISSING_ESSENTIALS in compute_flags(listing, ctx)


def test_missing_essentials_fires_when_address_and_snippet_missing() -> None:
    listing = _listing(address=None, photos=True, snippet=None)
    ctx = build_context([listing])
    assert QualityFlag.MISSING_ESSENTIALS in compute_flags(listing, ctx)


def test_missing_essentials_does_not_fire_when_only_address_missing() -> None:
    """Address missing but everything else present — listing is for-showing-only, not a scam."""
    listing = _listing(address=None, photos=True, snippet="A long enough description.")
    ctx = build_context([listing])
    assert QualityFlag.MISSING_ESSENTIALS not in compute_flags(listing, ctx)


def test_terse_no_address_requires_both_short_snippet_and_no_address() -> None:
    # Short snippet alone — doesn't fire (address still present).
    a = _listing(address="100 X St", snippet="rent")
    # Missing address alone — doesn't fire (snippet long enough).
    b = _listing(address=None, snippet="A normal-length description with details.")
    # Both — fires.
    c = _listing(address=None, snippet="rent")
    ctx = build_context([a, b, c])
    assert QualityFlag.TERSE_NO_ADDRESS not in compute_flags(a, ctx)
    assert QualityFlag.TERSE_NO_ADDRESS not in compute_flags(b, ctx)
    assert QualityFlag.TERSE_NO_ADDRESS in compute_flags(c, ctx)


def test_price_outlier_low_fires_when_two_sigma_below() -> None:
    # 5 normal 2BR craigslist listings around $3000 + one suspiciously cheap.
    pool = [_listing(price=p, source="craigslist", bedrooms=2) for p in [2900, 3000, 3050, 3100, 2950]]
    bad = _listing(price=400, source="craigslist", bedrooms=2)
    pool.append(bad)
    ctx = build_context(pool)
    assert QualityFlag.PRICE_OUTLIER_LOW in compute_flags(bad, ctx)


def test_price_outlier_low_does_not_fire_for_small_sample() -> None:
    pool = [_listing(price=3000), _listing(price=3500)]
    cheap = _listing(price=400)
    pool.append(cheap)
    ctx = build_context(pool)
    # Sample size of 3 — exactly at threshold but stdev is huge; bad won't be 2 sigma below.
    assert QualityFlag.PRICE_OUTLIER_LOW not in compute_flags(cheap, ctx)


def test_price_outlier_low_scoped_per_source() -> None:
    """A $2k listing on rentals_ca shouldn't flag because most REW.ca rows are $1M+."""
    rew_pool = [_listing(price=p, source="rew", bedrooms=2) for p in [1_200_000, 1_300_000, 1_400_000]]
    rental = _listing(price=2500, source="rentals_ca", bedrooms=2)
    rental_pool = [_listing(price=p, source="rentals_ca", bedrooms=2) for p in [2400, 2600, 2500]]
    ctx = build_context([*rew_pool, rental, *rental_pool])
    assert QualityFlag.PRICE_OUTLIER_LOW not in compute_flags(rental, ctx)


def test_duplicate_contact_fires_when_three_share_phone() -> None:
    phone_meta = {"contact_phone": "604-555-0100"}
    a = _listing(raw_metadata=phone_meta)
    b = _listing(raw_metadata=phone_meta)
    c = _listing(raw_metadata=phone_meta)
    ctx = build_context([a, b, c])
    assert QualityFlag.DUPLICATE_CONTACT in compute_flags(a, ctx)


def test_duplicate_contact_does_not_fire_for_two() -> None:
    phone_meta = {"contact_phone": "604-555-0100"}
    a = _listing(raw_metadata=phone_meta)
    b = _listing(raw_metadata=phone_meta)
    ctx = build_context([a, b])
    assert QualityFlag.DUPLICATE_CONTACT not in compute_flags(a, ctx)


def test_phash_collision_fires_across_canonical_ids() -> None:
    """Same photo phash, different canonical IDs = different listings sharing photos."""
    a = _listing(phash="abcd1234", canonical=str(uuid4()))
    b = _listing(phash="abcd1234", canonical=str(uuid4()))
    ctx = build_context([a, b])
    assert QualityFlag.PHOTO_PHASH_COLLISION in compute_flags(a, ctx)


def test_phash_collision_does_not_fire_for_same_canonical() -> None:
    """Same canonical = already dedup-merged as the same unit; not a quality issue."""
    shared = str(uuid4())
    a = _listing(phash="abcd1234", canonical=shared)
    b = _listing(phash="abcd1234", canonical=shared)
    ctx = build_context([a, b])
    assert QualityFlag.PHOTO_PHASH_COLLISION not in compute_flags(a, ctx)


def test_phone_in_description_snippet_counts() -> None:
    """Scammers sometimes paste the phone into the description body."""
    a = _listing(snippet="Call 604-555-0100 about the unit")
    b = _listing(snippet="Phone 604.555.0100 for showings")
    c = _listing(snippet="6045550100 — best to text")
    ctx = build_context([a, b, c])
    # All three normalize to the same 10-digit number.
    assert QualityFlag.DUPLICATE_CONTACT in compute_flags(a, ctx)


def test_flags_are_deterministic() -> None:
    pool = [_listing(price=p) for p in [2900, 3000, 3050, 3100, 2950]] + [_listing(price=400)]
    ctx1 = build_context(pool)
    ctx2 = build_context(pool)
    for listing in pool:
        assert compute_flags(listing, ctx1) == compute_flags(listing, ctx2)
