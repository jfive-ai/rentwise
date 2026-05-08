"""Pure scoring function tests."""

from __future__ import annotations

import pytest

from rentwise.dedup.scoring import (
    DEFAULT_THRESHOLD,
    PHASH_MATCH_THRESHOLD,
    PRICE_TOLERANCE_PCT,
    WEIGHT_ADDRESS,
    WEIGHT_BEDROOMS,
    WEIGHT_PHASH,
    WEIGHT_PRICE,
    Candidate,
    compute_confidence,
)


def _cand(
    *,
    canonical_id: str = "00000000-0000-0000-0000-000000000001",
    address: str | None = "1234 west 4th avenue vancouver bc",
    price: int | None = 2800,
    bedrooms: float | None = 2.0,
    phash: str | None = None,
) -> Candidate:
    return Candidate(
        canonical_id=canonical_id,
        address_normalized=address,
        price_cad=price,
        bedrooms=bedrooms,
        phash=phash,
    )


class TestEachWeightInIsolation:
    def test_zero_when_nothing_matches(self) -> None:
        a = _cand()
        b = _cand(address=None, price=None, bedrooms=None)
        assert compute_confidence(a, b) == 0.0

    def test_address_alone(self) -> None:
        a = _cand(price=None, bedrooms=None)
        b = _cand(price=None, bedrooms=None)
        assert compute_confidence(a, b) == pytest.approx(WEIGHT_ADDRESS)

    def test_price_alone(self) -> None:
        a = _cand(address=None, bedrooms=None)
        b = _cand(address=None, bedrooms=None)
        assert compute_confidence(a, b) == pytest.approx(WEIGHT_PRICE)

    def test_bedrooms_alone(self) -> None:
        a = _cand(address=None, price=None)
        b = _cand(address=None, price=None)
        assert compute_confidence(a, b) == pytest.approx(WEIGHT_BEDROOMS)

    def test_phash_alone(self) -> None:
        h = "0000000000000000"
        a = _cand(address=None, price=None, bedrooms=None, phash=h)
        b = _cand(address=None, price=None, bedrooms=None, phash=h)
        assert compute_confidence(a, b) == pytest.approx(WEIGHT_PHASH)


class TestPriceTolerance:
    def test_within_5_percent_matches(self) -> None:
        a = _cand(price=2800)
        b = _cand(price=2900)  # +3.6%
        assert compute_confidence(a, b) >= WEIGHT_ADDRESS + WEIGHT_PRICE

    def test_outside_tolerance_no_price_credit(self) -> None:
        a = _cand(price=2800, bedrooms=None)
        b = _cand(price=3500, bedrooms=None)  # +25%
        # Address still matches.
        assert compute_confidence(a, b) == pytest.approx(WEIGHT_ADDRESS)

    def test_zero_price_handling(self) -> None:
        a = _cand(price=0, bedrooms=None)
        b = _cand(price=0, bedrooms=None)
        # Address + price (both zero is "match")
        assert compute_confidence(a, b) == pytest.approx(WEIGHT_ADDRESS + WEIGHT_PRICE)

    def test_zero_vs_nonzero_no_price_credit(self) -> None:
        a = _cand(price=0, bedrooms=None)
        b = _cand(price=2500, bedrooms=None)
        assert compute_confidence(a, b) == pytest.approx(WEIGHT_ADDRESS)


class TestPhashTolerance:
    def test_close_phashes_match(self) -> None:
        # Two hashes differing in one bit are very close.
        a = _cand(address=None, price=None, bedrooms=None, phash="0000000000000000")
        b = _cand(address=None, price=None, bedrooms=None, phash="0000000000000001")
        assert compute_confidence(a, b) == pytest.approx(WEIGHT_PHASH)

    def test_far_phashes_no_credit(self) -> None:
        # Maximally different hashes (all-zeros vs all-ones) → 64 bits.
        a = _cand(address=None, price=None, bedrooms=None, phash="0000000000000000")
        b = _cand(address=None, price=None, bedrooms=None, phash="ffffffffffffffff")
        assert compute_confidence(a, b) == 0.0

    def test_missing_phash_no_credit(self) -> None:
        a = _cand(address=None, price=None, bedrooms=None, phash=None)
        b = _cand(address=None, price=None, bedrooms=None, phash="0000000000000000")
        assert compute_confidence(a, b) == 0.0


class TestThreshold:
    def test_two_strong_signals_clear_threshold(self) -> None:
        a = _cand()
        b = _cand()
        assert compute_confidence(a, b) >= DEFAULT_THRESHOLD

    def test_only_address_does_not_clear_threshold(self) -> None:
        # Address alone is 0.5; default threshold is 0.7.
        a = _cand(price=None, bedrooms=None)
        b = _cand(price=None, bedrooms=None)
        assert compute_confidence(a, b) < DEFAULT_THRESHOLD


class TestConstants:
    def test_weights_sum_at_least_threshold(self) -> None:
        # Sanity: the sum of every weight must clear the threshold,
        # otherwise even a perfect match wouldn't merge.
        total = WEIGHT_ADDRESS + WEIGHT_PRICE + WEIGHT_PHASH + WEIGHT_BEDROOMS
        assert total >= DEFAULT_THRESHOLD

    def test_constants_in_sensible_ranges(self) -> None:
        assert 0 < PRICE_TOLERANCE_PCT < 1
        assert 0 < PHASH_MATCH_THRESHOLD <= 64
