"""Digest narrative builder.

Issue #126 — the saved-search alert email used to be a bare list of new
listings. This module produces a structured ``Digest`` summary that
``compose_alert`` renders at the top of the email:

  > 3 new matches today. Top pick: <listing> — score 92, $2,950
  > Best on price: <listing> at $1,895 (15% below median).
  > ⚠ 1 listing has quality warnings.

Pure / deterministic — no live LLM dependency. (LLM polish is a
follow-up: pass the structured ``Digest`` into a single short
completion to read more naturally. The skeleton already works without
that.)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rentwise.models import NormalizedListing


@dataclass(frozen=True)
class DigestPick:
    """One per-axis recommendation pulled from the new listings."""

    listing: NormalizedListing
    reason: str


@dataclass
class Digest:
    count: int
    top_pick: DigestPick | None = None
    best_price: DigestPick | None = None
    flagged_count: int = 0
    # Already-rendered narrative paragraph. UI / email renderers can
    # use this verbatim or replace it with an LLM-rewrite in a follow-up.
    narrative: str = ""
    sources: list[str] = field(default_factory=list)


def _short_title(li: NormalizedListing) -> str:
    return li.title if len(li.title) <= 60 else li.title[:57] + "…"


def build_digest(new_listings: list[NormalizedListing]) -> Digest | None:
    """Return ``None`` when there's nothing to say (zero new listings)."""
    if not new_listings:
        return None

    n = len(new_listings)
    sources = sorted({item.source for item in new_listings})

    # Top pick: highest match_score (#119); fall back to the first row
    # when nothing was scored. Codex P2 on PR #134: the original code
    # documented the fallback but didn't implement it, so unscored
    # batches silently dropped the top-pick section.
    scored = [item for item in new_listings if item.match_score is not None]
    top_pick: DigestPick | None = None
    if scored:
        winner = max(scored, key=lambda item: item.match_score or 0)
        score = winner.match_score
        price = f" at ${winner.price_cad:,}" if winner.price_cad is not None else ""
        reason = f"score {score}{price}"
        top_pick = DigestPick(listing=winner, reason=reason)
    else:
        winner = new_listings[0]
        price = f" at ${winner.price_cad:,}" if winner.price_cad is not None else ""
        top_pick = DigestPick(listing=winner, reason=f"first new listing{price}")

    # Best-on-price: cheapest, but only when there are at least two priced
    # listings so the "best on price" framing means something.
    priced = [item for item in new_listings if item.price_cad is not None]
    best_price: DigestPick | None = None
    if len(priced) >= 2:
        cheapest = min(priced, key=lambda item: item.price_cad or 0)
        # Use the price-position chip (#123) when available so the framing
        # is "below median" not just "cheapest in this batch".
        pos_label = cheapest.price_position_label or ""
        if pos_label and "below median" in pos_label:
            reason = f"${cheapest.price_cad:,} — {pos_label}"
        else:
            reason = f"${cheapest.price_cad:,}"
        best_price = DigestPick(listing=cheapest, reason=reason)
    # Codex P2 on PR #134: drop best_price entirely when it points at the
    # same listing as top_pick so callers using the structured fields
    # don't see two picks for one listing — matches the rendered narrative.
    if best_price is not None and top_pick is not None and best_price.listing.id == top_pick.listing.id:
        best_price = None

    # Quality warnings (#120).
    flagged_count = sum(1 for item in new_listings if item.quality_flags)

    # Deterministic narrative paragraph — short, scannable, no LLM.
    pieces: list[str] = [
        f"{n} new match{'es' if n != 1 else ''} today."
    ]
    if top_pick is not None:
        pieces.append(
            f"Top pick: {_short_title(top_pick.listing)} ({top_pick.reason})."
        )
    if best_price is not None and (
        top_pick is None or best_price.listing.id != top_pick.listing.id
    ):
        pieces.append(
            f"Best on price: {_short_title(best_price.listing)} — {best_price.reason}."
        )
    if flagged_count > 0:
        verb = "carries" if flagged_count == 1 else "carry"
        pieces.append(
            f"⚠ {flagged_count} listing{'s' if flagged_count != 1 else ''}"
            f" {verb} quality warnings — review carefully."
        )

    return Digest(
        count=n,
        top_pick=top_pick,
        best_price=best_price,
        flagged_count=flagged_count,
        narrative=" ".join(pieces),
        sources=sources,
    )
