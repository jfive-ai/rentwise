"""Pure scoring functions for cross-source dedup.

Kept separate from :mod:`rentwise.dedup.service` so the math is
testable without an SQL session.
"""

from __future__ import annotations

from dataclasses import dataclass

from rentwise.enrichment.photo_hash import hamming_distance

# Weights — additive linear combination, threshold-gated. Tunable.
WEIGHT_ADDRESS = 0.5
WEIGHT_PRICE = 0.2
WEIGHT_PHASH = 0.3
WEIGHT_BEDROOMS = 0.1
DEFAULT_THRESHOLD = 0.7

# Within-X% match for price; tighter is more conservative.
PRICE_TOLERANCE_PCT = 0.05
# Hamming bound that counts as "same photo (possibly resized / re-encoded)".
PHASH_MATCH_THRESHOLD = 8


@dataclass(frozen=True)
class Candidate:
    canonical_id: str
    address_normalized: str | None
    price_cad: int | None
    bedrooms: float | None
    phash: str | None


def compute_confidence(a: Candidate, b: Candidate) -> float:
    """Sum of additive weights. Always in [0.0, 1.0]."""
    score = 0.0
    if _addresses_match(a.address_normalized, b.address_normalized):
        score += WEIGHT_ADDRESS
    if _prices_close(a.price_cad, b.price_cad, PRICE_TOLERANCE_PCT):
        score += WEIGHT_PRICE
    if _phashes_close(a.phash, b.phash, PHASH_MATCH_THRESHOLD):
        score += WEIGHT_PHASH
    if _bedrooms_match(a.bedrooms, b.bedrooms):
        score += WEIGHT_BEDROOMS
    return min(score, 1.0)


def _addresses_match(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return False
    return a == b


def _prices_close(a: int | None, b: int | None, tolerance: float) -> bool:
    if a is None or b is None:
        return False
    if a == 0 and b == 0:
        return True
    if a == 0 or b == 0:
        return False
    diff = abs(a - b)
    return diff / max(a, b) <= tolerance


def _phashes_close(a: str | None, b: str | None, max_distance: int) -> bool:
    d = hamming_distance(a, b)
    if d is None:
        return False
    return d <= max_distance


def _bedrooms_match(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return False
    return a == b
