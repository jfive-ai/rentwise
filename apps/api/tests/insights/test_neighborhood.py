"""Tests for the Neighborhood Insights aggregator (issue #124)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import HttpUrl

from rentwise.insights.neighborhood import compute_insights
from rentwise.models import (
    NormalizedListing,
    NormalizedQuery,
    SchoolCatchments,
    TransitInfo,
)


def _l(
    *,
    source: str = "craigslist",
    price: int | None = 2500,
    bedrooms: float | None = 2,
    neighborhood: str | None = "Kitsilano",
    transit: str | None = "Broadway-City Hall",
    schools: tuple[str | None, str | None, str | None] = ("Bayview", None, "Kits"),
) -> NormalizedListing:
    rid = str(uuid4())
    now = datetime.now(UTC)
    return NormalizedListing(
        id=rid,
        canonical_id=rid,
        source=source,
        source_url=HttpUrl(f"https://example.com/{rid}"),
        source_listing_id=rid,
        title=f"{neighborhood or 'X'} listing",
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
        nearest_transit=TransitInfo(nearest_stop_name=transit, walk_minutes=8) if transit else None,
        school_catchments=SchoolCatchments(
            elementary=schools[0], middle=schools[1], secondary=schools[2]
        ),
    )


def test_no_focus_returns_none() -> None:
    """Listings spread across 5 neighborhoods, no query — insights is None."""
    pool = [_l(neighborhood=n) for n in ("Kits", "Mt Pleasant", "Downtown", "East Van", "Renfrew")]
    assert compute_insights(pool, NormalizedQuery()) is None


def test_explicit_neighborhood_query_resolves_area() -> None:
    pool = [_l(neighborhood="Kitsilano") for _ in range(5)]
    insights = compute_insights(pool, NormalizedQuery(neighborhoods=["Kitsilano"]))
    assert insights is not None
    assert insights.area_name == "Kitsilano"
    assert insights.listing_count == 5


def test_mode_neighborhood_resolves_when_dominant() -> None:
    pool = [_l(neighborhood="Kitsilano") for _ in range(7)] + [
        _l(neighborhood="Downtown") for _ in range(2)
    ]
    insights = compute_insights(pool, NormalizedQuery())
    assert insights is not None
    assert insights.area_name == "Kitsilano"


def test_close_split_returns_none() -> None:
    """Without 60% dominance, the panel is suppressed."""
    pool = [_l(neighborhood="Kitsilano") for _ in range(5)] + [
        _l(neighborhood="Downtown") for _ in range(5)
    ]
    assert compute_insights(pool, NormalizedQuery()) is None


def test_median_rent_overall_and_by_bedrooms() -> None:
    pool = [
        _l(price=2500, bedrooms=2),
        _l(price=3000, bedrooms=2),
        _l(price=1800, bedrooms=1),
    ]
    insights = compute_insights(pool, NormalizedQuery(neighborhoods=["Kitsilano"]))
    assert insights is not None
    # Median of [2500, 3000, 1800] = 2500
    assert insights.median_rent_overall == 2500
    assert insights.median_rent_by_bedrooms.get("2BR") == 2750
    assert insights.median_rent_by_bedrooms.get("1BR") == 1800


def test_source_breakdown_counts_per_source() -> None:
    pool = [
        _l(source="craigslist"),
        _l(source="craigslist"),
        _l(source="livrent"),
    ]
    insights = compute_insights(pool, NormalizedQuery(neighborhoods=["Kitsilano"]))
    assert insights is not None
    assert insights.source_breakdown == {"craigslist": 2, "livrent": 1}


def test_nearby_skytrain_dedup_and_order() -> None:
    pool = [
        _l(transit="Broadway"),
        _l(transit="Broadway"),
        _l(transit="Broadway"),
        _l(transit="Olympic Village"),
        _l(transit=None),
    ]
    insights = compute_insights(pool, NormalizedQuery(neighborhoods=["Kitsilano"]))
    assert insights is not None
    # Most-common first.
    assert insights.nearby_skytrain_stations[0] == "Broadway"
    assert "Olympic Village" in insights.nearby_skytrain_stations


def test_schools_union_and_dedup() -> None:
    pool = [
        _l(schools=("A", None, "X")),
        _l(schools=("B", None, "X")),
        _l(schools=("A", "M", None)),
    ]
    insights = compute_insights(pool, NormalizedQuery(neighborhoods=["Kitsilano"]))
    assert insights is not None
    assert set(insights.schools) == {"A", "B", "X", "M"}
    # No duplicates.
    assert len(insights.schools) == 4
