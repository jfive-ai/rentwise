"""Tests for the price-position chip helper (issue #123)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import HttpUrl

from rentwise.models import NormalizedListing
from rentwise.scoring.price_position import (
    MIN_SAMPLE,
    PricePosition,
    compute_positions,
)


def _l(
    *,
    price: int | None,
    bedrooms: float | None,
    neighborhood: str | None = "Kitsilano",
    lid: str | None = None,
) -> NormalizedListing:
    rid = lid or str(uuid4())
    now = datetime.now(UTC)
    return NormalizedListing(
        id=rid,
        canonical_id=rid,
        source="test",
        source_url=HttpUrl(f"https://example.com/{rid}"),
        source_listing_id=rid,
        title=f"l{rid}",
        address=None,
        address_normalized=None,
        lat=None,
        lon=None,
        bedrooms=bedrooms,
        bathrooms=None,
        price_cad=price,
        pets_allowed=None,
        furnished=None,
        available_date=None,
        posted_at=now,
        last_seen_at=now,
        photos=[],
        description_snippet=None,
        neighborhood=neighborhood,
    )


def test_below_median_reports_negative_delta() -> None:
    pool = [_l(price=p, bedrooms=2) for p in (2500, 3000, 3500, 4000)]
    target = pool[0]  # $2500
    res = compute_positions(pool)[str(target.id)]
    assert res.delta_pct is not None and res.delta_pct < 0
    assert "below median" in res.label


def test_above_median_reports_positive_delta() -> None:
    pool = [_l(price=p, bedrooms=2) for p in (2000, 2500, 3000, 3500)]
    target = pool[-1]  # $3500
    res = compute_positions(pool)[str(target.id)]
    assert res.delta_pct is not None and res.delta_pct > 0
    assert "above median" in res.label


def test_near_median_reports_about_median() -> None:
    pool = [_l(price=p, bedrooms=2) for p in (2950, 3000, 3050, 3000)]
    target = pool[1]
    res = compute_positions(pool)[str(target.id)]
    assert res.label == "About median"


def test_low_sample_reports_not_enough() -> None:
    pool = [_l(price=2500, bedrooms=2), _l(price=3000, bedrooms=2)]
    target = pool[0]
    res = compute_positions(pool)[str(target.id)]
    assert res.sample_size < MIN_SAMPLE
    assert res.label == "Not enough comparables"


def test_unpriced_listing_returns_placeholder() -> None:
    pool = [_l(price=None, bedrooms=2)]
    target = pool[0]
    res = compute_positions(pool)[str(target.id)]
    assert res.delta_pct is None
    assert res.sample_size == 0


def test_no_neighborhood_returns_placeholder() -> None:
    """Codex P2 on PR #131 — ungeocoded rows aren't grouped so they
    don't get a "X% below median" chip from rows in unrelated areas."""
    pool = [_l(price=p, bedrooms=2, neighborhood=None) for p in (2500, 3000, 3500, 4000)]
    target = pool[0]
    res = compute_positions(pool)[str(target.id)]
    assert res.label == "Not enough comparables"
    assert res.delta_pct is None


def test_per_neighborhood_grouping() -> None:
    """A listing's bucket includes neighborhood — bumping prices in
    another neighborhood doesn't shift this one's median."""
    kits = [_l(price=p, bedrooms=2, neighborhood="Kitsilano") for p in (2900, 3000, 3100)]
    mp_target = _l(price=2000, bedrooms=2, neighborhood="Mt Pleasant")
    mp_pool = [_l(price=p, bedrooms=2, neighborhood="Mt Pleasant") for p in (2000, 2200, 2100, 2050)]
    res = compute_positions([*kits, mp_target, *mp_pool])[str(mp_target.id)]
    # Median in Mt Pleasant is ~2125. 2000 is ~-6%.
    assert res.delta_pct is not None
    assert -15 <= res.delta_pct <= 0


def test_returns_position_for_every_listing() -> None:
    pool = [_l(price=p, bedrooms=2) for p in (2500, 3000, 3500)]
    res = compute_positions(pool)
    assert {str(item.id) for item in pool} == set(res.keys())


def test_returned_struct_carries_sample_size() -> None:
    pool = [_l(price=p, bedrooms=2) for p in (2500, 3000, 3500, 4000)]
    res = compute_positions(pool)
    sizes = {r.sample_size for r in res.values()}
    assert 4 in sizes


def test_zero_median_does_not_explode() -> None:
    """Defensive: if every listing in the bucket has price=0 the median
    is 0 and a percentage is undefined. We return the placeholder."""
    pool = [_l(price=0, bedrooms=2) for _ in range(4)]
    res = compute_positions(pool)[str(pool[0].id)]
    assert res.label == "Not enough comparables"


def test_position_struct_dataclass() -> None:
    """Sanity test that PricePosition is importable and constructs."""
    p = PricePosition(sample_size=5, median=3000, delta_pct=-10, label="10% below median")
    assert p.median == 3000
