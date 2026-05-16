"""Price-position chip helper.

Issue #123 — every listing with a known price + bedrooms gets a small
"5% below median 2BR in this area" chip. Computed against the *active
result set* — no historical pricing data, no third-party API. The
chip degrades to a neutral "Not enough comparables" when fewer than 3
listings share the listing's (bedrooms, neighborhood) bucket.

Returned alongside the Match Score; same per-request lifetime.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from rentwise.models import NormalizedListing

# Minimum comparable count before we report a percentage. Anything
# below this and we surface "Not enough comparables yet" — saying
# "20 % below median" out of two data points would be statistical noise.
MIN_SAMPLE = 3


@dataclass(frozen=True)
class PricePosition:
    """Per-listing market-position result.

    ``delta_pct`` is positive for above-median, negative for below.
    ``label`` is the user-facing string the chip renders.
    """

    sample_size: int
    median: int | None
    delta_pct: int | None
    label: str


def _bucket(listing: NormalizedListing) -> tuple[float | None, str | None]:
    """Bucket key — same (bedrooms, neighborhood) shape the chip groups by.

    bedrooms is rounded to 0.5 so studios (0.5) and 1BRs (1.0) don't
    accidentally combine; 1.5BRs land with 1.0 if the source rounds
    that way. Neighborhood comes from enrichment (City of Vancouver
    GeoJSON) — None for listings that didn't geocode inside the city.
    """
    beds = listing.bedrooms
    bucket_beds = round(beds * 2) / 2 if beds is not None else None
    return (bucket_beds, listing.neighborhood)


def _format_label(delta_pct: int | None, sample: int) -> str:
    if sample < MIN_SAMPLE or delta_pct is None:
        return "Not enough comparables"
    if abs(delta_pct) <= 3:
        return "About median"
    if delta_pct < 0:
        return f"{-delta_pct}% below median"
    return f"{delta_pct}% above median"


def compute_positions(
    listings: list[NormalizedListing],
) -> dict[str, PricePosition]:
    """Return a {listing.id (str): PricePosition} map.

    Listings with no price or no bedrooms aren't groupable, so they
    get the "Not enough comparables" placeholder (sample_size = 0).
    """
    # Group prices per bucket.
    grouped: dict[tuple[float | None, str | None], list[int]] = {}
    for listing in listings:
        if listing.price_cad is None or listing.bedrooms is None:
            continue
        grouped.setdefault(_bucket(listing), []).append(listing.price_cad)

    medians = {
        k: int(statistics.median(prices))
        for k, prices in grouped.items()
        if len(prices) >= 1
    }
    samples = {k: len(prices) for k, prices in grouped.items()}

    out: dict[str, PricePosition] = {}
    for listing in listings:
        lid = str(listing.id)
        if listing.price_cad is None or listing.bedrooms is None:
            out[lid] = PricePosition(
                sample_size=0,
                median=None,
                delta_pct=None,
                label="Not enough comparables",
            )
            continue
        key = _bucket(listing)
        sample = samples.get(key, 0)
        median = medians.get(key)
        if sample < MIN_SAMPLE or median is None or median == 0:
            out[lid] = PricePosition(
                sample_size=sample,
                median=median,
                delta_pct=None,
                label="Not enough comparables",
            )
            continue
        delta = round(((listing.price_cad - median) / median) * 100)
        out[lid] = PricePosition(
            sample_size=sample,
            median=median,
            delta_pct=delta,
            label=_format_label(delta, sample),
        )
    return out
