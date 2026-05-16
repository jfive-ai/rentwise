"""Tests for the Match Score (issue #119).

Each test pins one axis of the rubric. Together they enforce the
formula contract documented in :mod:`rentwise.scoring.match`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pydantic import HttpUrl

from rentwise.models import (
    FurnishedPolicy,
    NormalizedListing,
    NormalizedQuery,
    PetPolicy,
    TransitInfo,
)
from rentwise.scoring.match import (
    W_BEDROOMS,
    W_COMPLETENESS,
    W_FRESHNESS,
    W_NEIGHBORHOOD,
    W_POLICIES,
    W_PRICE,
    W_TRANSIT,
    explain,
    score_bedrooms,
    score_completeness,
    score_freshness,
    score_listing,
    score_neighborhood,
    score_policies,
    score_price,
    score_transit,
)

_FIXED_NOW = datetime(2026, 5, 16, 0, 0, 0, tzinfo=UTC)


def _make_listing(
    *,
    price: int | None = 2500,
    bedrooms: float | None = 2,
    address: str | None = "100 Test St, Vancouver, BC",
    photos: bool = True,
    snippet: str | None = "A great place",
    neighborhood: str | None = "Kitsilano",
    transit_walk: int | None = None,
    posted_offset_days: float = 0.0,
    pets_allowed: bool | None = None,
    furnished: bool | None = None,
) -> NormalizedListing:
    lid = uuid4()
    return NormalizedListing(
        id=lid,
        canonical_id=lid,
        source="test",
        source_url=HttpUrl("https://example.com/abc"),
        source_listing_id="abc",
        title="A 2BR apartment",
        address=address,
        address_normalized=None,
        lat=49.27,
        lon=-123.16,
        bedrooms=bedrooms,
        bathrooms=1,
        price_cad=price,
        pets_allowed=pets_allowed,
        furnished=furnished,
        available_date=None,
        posted_at=_FIXED_NOW - timedelta(days=posted_offset_days),
        last_seen_at=_FIXED_NOW,
        photos=[HttpUrl("https://example.com/p.jpg")] if photos else [],
        description_snippet=snippet,
        neighborhood=neighborhood,
        nearest_transit=(
            TransitInfo(nearest_stop_name="Main St-Sci World", walk_minutes=transit_walk)
            if transit_walk is not None
            else None
        ),
    )


# ----- price ----------------------------------------------------------


def test_price_no_constraint_returns_full_weight() -> None:
    listing = _make_listing(price=999999)
    assert score_price(listing, NormalizedQuery()) == W_PRICE


def test_price_missing_with_constraint_returns_zero() -> None:
    listing = _make_listing(price=None)
    assert score_price(listing, NormalizedQuery(price_max=3000)) == 0


def test_price_at_midpoint_returns_full_weight() -> None:
    listing = _make_listing(price=2500)
    q = NormalizedQuery(price_min=2000, price_max=3000)
    assert score_price(listing, q) == W_PRICE


def test_price_at_bound_returns_zero() -> None:
    listing = _make_listing(price=3000)
    q = NormalizedQuery(price_min=2000, price_max=3000)
    assert score_price(listing, q) == 0


def test_price_above_bound_returns_zero() -> None:
    listing = _make_listing(price=4000)
    q = NormalizedQuery(price_max=3000)
    assert score_price(listing, q) == 0


def test_price_within_open_bound_scores_full() -> None:
    """Only price_max set, price below it → full weight (no midpoint to fall off)."""
    listing = _make_listing(price=2000)
    q = NormalizedQuery(price_max=3000)
    assert score_price(listing, q) == W_PRICE


# ----- bedrooms -------------------------------------------------------


def test_bedrooms_exact_match() -> None:
    listing = _make_listing(bedrooms=2)
    q = NormalizedQuery(bedrooms_min=2, bedrooms_max=2)
    assert score_bedrooms(listing, q) == W_BEDROOMS


def test_bedrooms_unknown_with_constraint() -> None:
    listing = _make_listing(bedrooms=None)
    assert score_bedrooms(listing, NormalizedQuery(bedrooms_min=1)) == 0


def test_bedrooms_no_constraint() -> None:
    listing = _make_listing(bedrooms=2)
    assert score_bedrooms(listing, NormalizedQuery()) == W_BEDROOMS


# ----- transit --------------------------------------------------------


def test_transit_under_cap_is_full() -> None:
    listing = _make_listing(transit_walk=5)
    assert score_transit(listing, NormalizedQuery(transit_max_walk_minutes=10)) == W_TRANSIT


def test_transit_over_cap_decays() -> None:
    listing = _make_listing(transit_walk=15)
    q = NormalizedQuery(transit_max_walk_minutes=10)
    s = score_transit(listing, q)
    assert 0 < s < W_TRANSIT


def test_transit_double_cap_is_zero() -> None:
    listing = _make_listing(transit_walk=20)
    assert score_transit(listing, NormalizedQuery(transit_max_walk_minutes=10)) == 0


def test_transit_no_constraint_is_full() -> None:
    listing = _make_listing(transit_walk=None)
    assert score_transit(listing, NormalizedQuery()) == W_TRANSIT


def test_transit_unknown_with_constraint_is_half() -> None:
    listing = _make_listing(transit_walk=None)
    assert score_transit(listing, NormalizedQuery(transit_max_walk_minutes=10)) == W_TRANSIT // 2


# ----- neighborhood ---------------------------------------------------


def test_neighborhood_match() -> None:
    listing = _make_listing(neighborhood="Kitsilano")
    q = NormalizedQuery(neighborhoods=["Kitsilano"])
    assert score_neighborhood(listing, q) == W_NEIGHBORHOOD


def test_neighborhood_mismatch_is_zero() -> None:
    listing = _make_listing(neighborhood="Mount Pleasant")
    q = NormalizedQuery(neighborhoods=["Kitsilano"])
    assert score_neighborhood(listing, q) == 0


def test_neighborhood_unknown_is_half() -> None:
    listing = _make_listing(neighborhood=None)
    q = NormalizedQuery(neighborhoods=["Kitsilano"])
    assert score_neighborhood(listing, q) == W_NEIGHBORHOOD // 2


def test_neighborhood_no_query_is_full() -> None:
    listing = _make_listing(neighborhood=None)
    assert score_neighborhood(listing, NormalizedQuery()) == W_NEIGHBORHOOD


# ----- freshness ------------------------------------------------------


def test_freshness_today_is_full() -> None:
    listing = _make_listing(posted_offset_days=0)
    assert score_freshness(listing, now=_FIXED_NOW) == W_FRESHNESS


def test_freshness_fortnight_is_zero() -> None:
    listing = _make_listing(posted_offset_days=14)
    assert score_freshness(listing, now=_FIXED_NOW) == 0


def test_freshness_midway() -> None:
    listing = _make_listing(posted_offset_days=7)
    s = score_freshness(listing, now=_FIXED_NOW)
    assert 4 <= s <= 6


# ----- completeness ---------------------------------------------------


def test_completeness_full() -> None:
    listing = _make_listing()
    assert score_completeness(listing) == W_COMPLETENESS


def test_completeness_no_address() -> None:
    listing = _make_listing(address=None)
    assert score_completeness(listing) == W_COMPLETENESS - 3


def test_completeness_all_missing_is_zero() -> None:
    listing = _make_listing(address=None, photos=False, snippet=None)
    assert score_completeness(listing) == 0


# ----- policies -------------------------------------------------------


def test_policies_pets_required_listing_disallows() -> None:
    listing = _make_listing(pets_allowed=False)
    q = NormalizedQuery(pets=PetPolicy.REQUIRED)
    assert score_policies(listing, q) == 0


def test_policies_pets_unknown_is_full() -> None:
    """No data on the listing → full marks (don't penalize uncertainty)."""
    listing = _make_listing(pets_allowed=None)
    q = NormalizedQuery(pets=PetPolicy.REQUIRED)
    assert score_policies(listing, q) == W_POLICIES


def test_policies_furnished_mismatch() -> None:
    listing = _make_listing(furnished=False)
    q = NormalizedQuery(furnished=FurnishedPolicy.YES)
    assert score_policies(listing, q) == 0


# ----- end-to-end -----------------------------------------------------


def test_empty_query_scores_full() -> None:
    listing = _make_listing()
    s = score_listing(listing, NormalizedQuery(), now=_FIXED_NOW)
    assert s.total == 100


def test_max_score_never_exceeds_100() -> None:
    listing = _make_listing()
    s = score_listing(listing, NormalizedQuery(price_max=3000), now=_FIXED_NOW)
    assert 0 <= s.total <= 100


def test_explain_prefers_constraint_axes_over_always_on() -> None:
    listing = _make_listing()
    q = NormalizedQuery(price_max=3000)
    s = score_listing(listing, q, now=_FIXED_NOW)
    text = explain(s, q)
    assert "in your price range" in text


def test_explain_handles_weak_match() -> None:
    listing = _make_listing(price=4000)
    q = NormalizedQuery(price_max=3000)
    s = score_listing(listing, q, now=_FIXED_NOW)
    text = explain(s, q)
    assert "out of price range" in text
