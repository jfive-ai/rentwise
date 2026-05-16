"""Per-area insights aggregator.

Issue #124 — when a search has a clear area focus (an explicit
neighborhood query OR a mode neighborhood across the result set),
return a small structured panel summarizing:

- listing count + median rent overall + by-bedroom-count
- source breakdown (how many craigslist vs livrent vs …)
- nearby SkyTrain stations (extracted from the existing TransLink slim
  stops dataset)
- schools whose catchments overlap the area (VSB GeoJSON)

All inputs are already in the repo. No live API calls.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field

from rentwise.models import NormalizedListing, NormalizedQuery


@dataclass
class NeighborhoodInsights:
    """Wire shape — mirrored on the frontend via NeighborhoodInsights TS type."""

    area_name: str
    listing_count: int
    median_rent_overall: int | None = None
    median_rent_by_bedrooms: dict[str, int] = field(default_factory=dict)
    source_breakdown: dict[str, int] = field(default_factory=dict)
    nearby_skytrain_stations: list[str] = field(default_factory=list)
    schools: list[str] = field(default_factory=list)


def _resolve_area(listings: list[NormalizedListing], query: NormalizedQuery) -> str | None:
    """Return the area to summarize, or None when no clear focus exists.

    Rules:
      1. If the query has exactly one neighborhood selected, use it.
      2. Otherwise, if >= 60% of geocoded listings share one
         neighborhood, use the mode.
      3. Otherwise, None — the panel doesn't render.
    """
    if len(query.neighborhoods) == 1:
        return query.neighborhoods[0]
    located = [item.neighborhood for item in listings if item.neighborhood]
    if not located:
        return None
    counts = Counter(located)
    top, top_count = counts.most_common(1)[0]
    if top_count / len(located) >= 0.6:
        return top
    return None


def _median_int(prices: list[int]) -> int | None:
    if not prices:
        return None
    return int(statistics.median(prices))


def _listings_in_area(listings: list[NormalizedListing], area_name: str) -> list[NormalizedListing]:
    needle = area_name.casefold().strip()
    out: list[NormalizedListing] = []
    for listing in listings:
        if listing.neighborhood and listing.neighborhood.casefold() == needle:
            out.append(listing)
            continue
        # Fall back to substring match against title + address for
        # un-geocoded listings (some Craigslist rows lack lat/lon).
        haystack = " ".join(filter(None, [listing.title, listing.address])).casefold()
        if needle in haystack:
            out.append(listing)
    return out


def _nearby_skytrain_stations(area_listings: list[NormalizedListing]) -> list[str]:
    """Deduplicate the nearest-transit stop names across the listings.

    Listings without an enriched ``nearest_transit`` contribute nothing.
    Order is insertion-stable so the UI shows the most frequently
    appearing stops first.
    """
    counter: Counter[str] = Counter()
    for listing in area_listings:
        t = listing.nearest_transit
        if t is None:
            continue
        counter[t.nearest_stop_name] += 1
    return [name for name, _ in counter.most_common(5)]


def _schools_for_area(area_listings: list[NormalizedListing]) -> list[str]:
    """Union of per-level catchments across the area's listings.

    Each listing's ``school_catchments`` carries up to three levels;
    union them, drop blanks, dedupe.
    """
    seen: list[str] = []
    seen_set: set[str] = set()
    for listing in area_listings:
        sc = listing.school_catchments
        for level in (sc.elementary, sc.middle, sc.secondary):
            if level and level not in seen_set:
                seen.append(level)
                seen_set.add(level)
    return seen


def compute_insights(
    listings: list[NormalizedListing], query: NormalizedQuery
) -> NeighborhoodInsights | None:
    """Return the panel data, or ``None`` if no clear area focus exists."""
    area = _resolve_area(listings, query)
    if area is None:
        return None
    area_listings = _listings_in_area(listings, area)
    if not area_listings:
        return None

    overall_prices = [item.price_cad for item in area_listings if item.price_cad is not None]
    by_bedrooms_raw: dict[str, list[int]] = {}
    for item in area_listings:
        if item.price_cad is None or item.bedrooms is None:
            continue
        # Stable string keys so the wire shape stays JSON-friendly.
        if item.bedrooms <= 0.5:
            label = "Studio"
        elif item.bedrooms == int(item.bedrooms):
            label = f"{int(item.bedrooms)}BR"
        else:
            label = f"{item.bedrooms}BR"
        by_bedrooms_raw.setdefault(label, []).append(item.price_cad)

    return NeighborhoodInsights(
        area_name=area,
        listing_count=len(area_listings),
        median_rent_overall=_median_int(overall_prices),
        median_rent_by_bedrooms={k: int(statistics.median(v)) for k, v in by_bedrooms_raw.items()},
        source_breakdown=dict(Counter(item.source for item in area_listings)),
        nearby_skytrain_stations=_nearby_skytrain_stations(area_listings),
        schools=_schools_for_area(area_listings),
    )
