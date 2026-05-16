"""Deterministic Match Score for ranking listings against a query.

Issue #119 — competitors (Zillow Zestimate, Redfin Hot Homes) reduce
multi-axis fit to a single number. We do the same with a transparent,
testable, no-live-LLM formula:

    weight   field
    ------   -----------------------------------------------------
    30       price fit against [price_min, price_max]
    15       bedroom fit against [bedrooms_min, bedrooms_max]
    15       transit walk minutes vs transit_max_walk_minutes
    15       neighborhood (geocoded inside one of query.neighborhoods)
    10       freshness — fraction of 14 days since posted
    10       completeness — address, photo, snippet present
     5       pets / furnished honored
    ----
   100       max

When a query field is unset, that axis is "neutral" — every listing gets
the *full* weight for it. That way an empty query scores everything at
100 (no constraint to violate). The score never goes negative or above
100; the explanation is the top contributing factor in plain English.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from rentwise.models import (
    FurnishedPolicy,
    NormalizedListing,
    NormalizedQuery,
    PetPolicy,
)

# Weight per axis. Must sum to 100.
W_PRICE = 30
W_BEDROOMS = 15
W_TRANSIT = 15
W_NEIGHBORHOOD = 15
W_FRESHNESS = 10
W_COMPLETENESS = 10
W_POLICIES = 5
TOTAL_WEIGHT = W_PRICE + W_BEDROOMS + W_TRANSIT + W_NEIGHBORHOOD + W_FRESHNESS + W_COMPLETENESS + W_POLICIES
assert TOTAL_WEIGHT == 100, "Match score weights must sum to 100"


@dataclass(frozen=True)
class ScoreBreakdown:
    """Per-axis contribution to a listing's Match Score.

    Returned by :func:`score_listing` alongside the rolled-up integer.
    Used by the frontend to render a "why" badge and by tests to verify
    each axis independently of the others.
    """

    price: int
    bedrooms: int
    transit: int
    neighborhood: int
    freshness: int
    completeness: int
    policies: int

    @property
    def total(self) -> int:
        return (
            self.price
            + self.bedrooms
            + self.transit
            + self.neighborhood
            + self.freshness
            + self.completeness
            + self.policies
        )


def _midpoint_score(value: float, lo: float | None, hi: float | None, weight: int) -> int:
    """Full marks at the midpoint; linear penalty toward each bound; 0 outside.

    Works for both ``price`` (where lo/hi might be set independently) and
    ``bedrooms``. When only one bound is set, the score is full inside the
    constraint and decays beyond it.
    """
    if lo is None and hi is None:
        return weight  # No constraint = neutral, full weight.
    if lo is not None and value < lo:
        return 0
    if hi is not None and value > hi:
        return 0
    if lo is not None and hi is not None:
        if lo == hi:
            return weight
        mid = (lo + hi) / 2
        half_range = (hi - lo) / 2
        distance = abs(value - mid)
        return round(weight * max(0.0, 1.0 - distance / half_range))
    return weight


def score_price(listing: NormalizedListing, query: NormalizedQuery) -> int:
    """Score the listing's price against [price_min, price_max].

    Unpriced rows score 0 when *any* price constraint is set — we can't
    confirm they fit. Without a constraint they get the full weight.
    """
    if query.price_min is None and query.price_max is None:
        return W_PRICE
    if listing.price_cad is None:
        return 0
    return _midpoint_score(listing.price_cad, query.price_min, query.price_max, W_PRICE)


def score_bedrooms(listing: NormalizedListing, query: NormalizedQuery) -> int:
    if query.bedrooms_min is None and query.bedrooms_max is None:
        return W_BEDROOMS
    if listing.bedrooms is None:
        return 0
    return _midpoint_score(listing.bedrooms, query.bedrooms_min, query.bedrooms_max, W_BEDROOMS)


def score_transit(listing: NormalizedListing, query: NormalizedQuery) -> int:
    """Penalize walk minutes above the user's max; degrade linearly to 0 at 2x."""
    if query.transit_max_walk_minutes is None:
        return W_TRANSIT
    transit = listing.nearest_transit
    if transit is None:
        # The user asked for transit-near, the row has no transit data.
        # Half-credit — neither confirmed-fit nor confirmed-bad.
        return W_TRANSIT // 2
    walk = transit.walk_minutes
    cap = query.transit_max_walk_minutes
    if walk <= cap:
        return W_TRANSIT
    # 2x cap → 0 marks.
    excess = walk - cap
    return round(W_TRANSIT * max(0.0, 1.0 - excess / cap))


def score_neighborhood(listing: NormalizedListing, query: NormalizedQuery) -> int:
    """Full marks when geocoded into one of the requested polygons.

    Without a neighborhood constraint, every listing gets full weight.
    With a constraint but no geocode, half-credit.
    """
    if not query.neighborhoods:
        return W_NEIGHBORHOOD
    wanted = {n.casefold().strip() for n in query.neighborhoods}
    have = (listing.neighborhood or "").casefold().strip()
    if have and have in wanted:
        return W_NEIGHBORHOOD
    if not have:
        return W_NEIGHBORHOOD // 2
    return 0


def score_freshness(listing: NormalizedListing, *, now: datetime | None = None) -> int:
    """Linear decay over 14 days. Newer listings score higher.

    Listings missing ``posted_at`` would already have been rejected at
    ingest (the field is non-optional on RawListing), but we guard
    against it anyway and treat unknown as half-credit.
    """
    now = now or datetime.now(UTC)
    posted = listing.posted_at
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=UTC)
    age_days = max(0.0, (now - posted).total_seconds() / 86400)
    if age_days >= 14:
        return 0
    return round(W_FRESHNESS * (1 - age_days / 14))


def score_completeness(listing: NormalizedListing) -> int:
    """Three signals — address, photo, description snippet. Each missing one drops 3 pts."""
    score = W_COMPLETENESS
    if not listing.address:
        score -= 3
    if not listing.photos:
        score -= 3
    if not listing.description_snippet:
        score -= 3
    # Floor at 0 — losing 9 of 10 takes us to 1; we want 0 when nothing's present.
    if not listing.address and not listing.photos and not listing.description_snippet:
        score = 0
    return max(0, score)


def score_policies(listing: NormalizedListing, query: NormalizedQuery) -> int:
    """Pets + furnished — full marks unless the listing explicitly contradicts."""
    score = W_POLICIES
    # Pets
    if query.pets in (PetPolicy.REQUIRED, PetPolicy.OK):
        if listing.pets_allowed is False:
            return 0
    elif query.pets == PetPolicy.NO:
        if listing.pets_allowed is True:
            return 0
    # Furnished
    if query.furnished == FurnishedPolicy.YES and listing.furnished is False:
        return 0
    if query.furnished == FurnishedPolicy.NO and listing.furnished is True:
        return 0
    return score


def score_listing(
    listing: NormalizedListing,
    query: NormalizedQuery,
    *,
    now: datetime | None = None,
) -> ScoreBreakdown:
    """Compute every axis. Caller can roll up via ``ScoreBreakdown.total``."""
    return ScoreBreakdown(
        price=score_price(listing, query),
        bedrooms=score_bedrooms(listing, query),
        transit=score_transit(listing, query),
        neighborhood=score_neighborhood(listing, query),
        freshness=score_freshness(listing, now=now),
        completeness=score_completeness(listing),
        policies=score_policies(listing, query),
    )


def explain(breakdown: ScoreBreakdown, query: NormalizedQuery) -> str:
    """Return a short user-facing string describing why this score landed.

    A user-constrained axis that scores zero is the most informative
    signal — "out of price range" trumps "fresh listing" because it's
    why the score is low. So we surface the negative *first* when a
    requested axis fails outright; only when no constraint is failing
    do we fall through to the top positive contributors.
    """
    # Constraint-failures take precedence — they explain low scores.
    if (
        query.price_min is not None or query.price_max is not None
    ) and breakdown.price == 0:
        return "out of price range"
    if (
        query.bedrooms_min is not None or query.bedrooms_max is not None
    ) and breakdown.bedrooms == 0:
        return "wrong bedroom count"
    if query.neighborhoods and breakdown.neighborhood == 0:
        return "not in your neighborhood"

    candidates: list[tuple[str, float]] = []
    if query.price_min is not None or query.price_max is not None:
        candidates.append(("in your price range", breakdown.price / W_PRICE))
    if query.bedrooms_min is not None or query.bedrooms_max is not None:
        candidates.append(("right bedroom count", breakdown.bedrooms / W_BEDROOMS))
    if query.transit_max_walk_minutes is not None:
        candidates.append(("near transit", breakdown.transit / W_TRANSIT))
    if query.neighborhoods:
        candidates.append(("in your neighborhood", breakdown.neighborhood / W_NEIGHBORHOOD))
    # Always-on signals
    candidates.append(("fresh listing", breakdown.freshness / W_FRESHNESS))
    candidates.append(("complete details", breakdown.completeness / W_COMPLETENESS))

    # Keep only positive contributors, sort by fractional fill desc.
    positives = [(label, frac) for label, frac in candidates if frac > 0.5]
    positives.sort(key=lambda lf: -lf[1])

    if not positives:
        if breakdown.completeness == 0:
            return "missing key details"
        return "weak match"

    top = positives[:2]
    return ", ".join(label for label, _ in top)
