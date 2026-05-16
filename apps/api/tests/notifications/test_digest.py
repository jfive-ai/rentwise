"""Tests for the saved-search digest narrative (issue #126)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import HttpUrl

from rentwise.models import NormalizedListing
from rentwise.notifications.digest import build_digest


def _l(
    *,
    title: str = "Listing",
    price: int | None = 2500,
    bedrooms: float | None = 2,
    source: str = "craigslist",
    match_score: int | None = 80,
    price_position: str | None = None,
    quality_flags: list[str] | None = None,
) -> NormalizedListing:
    lid = str(uuid4())
    now = datetime.now(UTC)
    return NormalizedListing(
        id=lid,
        canonical_id=lid,
        source=source,
        source_url=HttpUrl(f"https://example.com/{lid}"),
        source_listing_id=lid,
        title=title,
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
        match_score=match_score,
        price_position_label=price_position,
        quality_flags=quality_flags or [],
    )


def test_empty_returns_none() -> None:
    assert build_digest([]) is None


def test_count_phrase_singular_vs_plural() -> None:
    one = build_digest([_l()])
    assert one is not None
    assert "1 new match today" in one.narrative
    three = build_digest([_l(), _l(), _l()])
    assert three is not None
    assert "3 new matches today" in three.narrative


def test_top_pick_is_highest_match_score() -> None:
    a = _l(title="A", match_score=70)
    b = _l(title="B", match_score=95)
    c = _l(title="C", match_score=80)
    d = build_digest([a, b, c])
    assert d is not None
    assert d.top_pick is not None
    assert d.top_pick.listing.title == "B"
    assert "score 95" in d.top_pick.reason


def test_best_price_when_two_or_more_priced() -> None:
    a = _l(title="A", price=2500, match_score=70)
    b = _l(title="B", price=1900, match_score=60)
    d = build_digest([a, b])
    assert d is not None
    assert d.best_price is not None
    assert d.best_price.listing.title == "B"


def test_best_price_skipped_when_only_one_priced() -> None:
    d = build_digest([_l(price=2500), _l(price=None)])
    assert d is not None
    assert d.best_price is None


def test_best_price_skipped_when_same_as_top_pick() -> None:
    """If the cheapest also has the highest match score, don't repeat it."""
    a = _l(title="A", price=2500, match_score=60)
    b = _l(title="B", price=1900, match_score=95)
    d = build_digest([a, b])
    assert d is not None
    assert d.top_pick is not None and d.top_pick.listing.title == "B"
    assert "Best on price" not in d.narrative
    # Codex P2 on PR #134: structured field must also be cleared so
    # downstream consumers (LLM rewrite layer, alt UI) see consistent
    # data, not two picks for the same listing.
    assert d.best_price is None


def test_top_pick_falls_back_when_no_match_scores() -> None:
    """Codex P2 on PR #134: when no listing has a match_score, the
    digest should surface the first listing as the top pick instead
    of silently dropping the section."""
    a = _l(title="A", price=2500, match_score=None)
    b = _l(title="B", price=1900, match_score=None)
    d = build_digest([a, b])
    assert d is not None
    assert d.top_pick is not None
    assert d.top_pick.listing.title == "A"
    assert "Top pick" in d.narrative


def test_flagged_count_surfaces_in_narrative() -> None:
    a = _l(quality_flags=["price_outlier_low"])
    b = _l()
    c = _l(quality_flags=["missing_essentials"])
    d = build_digest([a, b, c])
    assert d is not None
    assert d.flagged_count == 2
    assert "⚠" in d.narrative
    assert "2 listings" in d.narrative


def test_uses_price_position_when_below_median() -> None:
    # A is the top match (highest score), B is the cheapest with a
    # below-median chip — different listings so best_price isn't dropped.
    a = _l(title="A", price=2500, match_score=80)
    b = _l(title="B", price=1900, match_score=70, price_position="20% below median")
    d = build_digest([a, b])
    assert d is not None
    assert d.best_price is not None
    assert "20% below median" in d.best_price.reason


def test_sources_listed_alphabetically() -> None:
    d = build_digest(
        [_l(source="livrent"), _l(source="craigslist"), _l(source="rentals_ca")]
    )
    assert d is not None
    assert d.sources == ["craigslist", "livrent", "rentals_ca"]
