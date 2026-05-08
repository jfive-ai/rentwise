"""DedupService: assign a shared canonical_id across listings of the same property.

Algorithm (per Phase 4 PR-C design in #35):

1. Look up candidate listings keyed on ``address_normalized`` (the
   index from migration 0006 makes this O(log n + k) where k is the
   match cardinality, typically very small).
2. Score each candidate against the new listing using
   :func:`compute_confidence`. Weights are hand-tuned constants —
   tunable in PR-D once we see real false positive / negative rates.
3. If the best score ≥ ``threshold``, reuse that listing's
   canonical_id. Otherwise leave the new listing self-canonical.

Exclusions:

- Same ``(source, source_listing_id)`` short-circuits before getting
  here (the upsert path returns the same row).
- Listings without ``address_normalized`` skip dedup — there's no
  candidate index to consult.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.dedup.scoring import (
    DEFAULT_THRESHOLD,
    Candidate,
    compute_confidence,
)
from rentwise.models import NormalizedListing
from rentwise.storage.models import Listing

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class DedupConfig:
    enabled: bool = True
    threshold: float = DEFAULT_THRESHOLD
    max_candidates: int = 20


class DedupService:
    """Assigns ``canonical_id`` to incoming listings during ingestion.

    The service does **not** persist anything itself — callers (the
    aggregator) take the returned listing and pass it to ``ListingRepo``.
    """

    def __init__(self, session: AsyncSession, *, config: DedupConfig | None = None) -> None:
        self.session = session
        self.config = config or DedupConfig()

    async def assign_canonical(self, listing: NormalizedListing) -> NormalizedListing:
        if not self.config.enabled:
            return listing
        if not listing.address_normalized:
            return listing

        candidates = await self._lookup_candidates(
            address_key=listing.address_normalized,
            phash=listing.phash,
            exclude_source=listing.source,
            exclude_source_listing_id=listing.source_listing_id,
        )
        if not candidates:
            return listing

        # Score and pick the best.
        best: tuple[float, Candidate] | None = None
        for cand in candidates:
            score = compute_confidence(_to_candidate(listing), cand)
            if best is None or score > best[0]:
                best = (score, cand)
        if best is None:
            return listing
        score, winner = best
        if score < self.config.threshold:
            return listing

        log.info(
            "dedup.assigned",
            address=listing.address_normalized,
            score=round(score, 2),
            into=winner.canonical_id,
        )
        return listing.model_copy(update={"canonical_id": _uuid_from_str(winner.canonical_id)})

    async def _lookup_candidates(
        self,
        *,
        address_key: str,
        phash: str | None,
        exclude_source: str,
        exclude_source_listing_id: str,
    ) -> list[Candidate]:
        """Pull rows that share an address (the strongest single signal).

        We deliberately don't include phash-only candidates here. If two
        listings have wildly different addresses but the same photo, that's
        more likely a stock photo than a true duplicate; address-anchored
        scoring with phash as a contributor is the conservative choice.
        """
        stmt = (
            select(Listing)
            .where(Listing.address_normalized == address_key)
            .limit(self.config.max_candidates)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            _to_candidate_from_row(row)
            for row in rows
            if not (
                row.source == exclude_source and row.source_listing_id == exclude_source_listing_id
            )
        ]


# ---------------------------------------------------------------------------
# Helpers — keep the service body readable
# ---------------------------------------------------------------------------


def _to_candidate(listing: NormalizedListing) -> Candidate:
    return Candidate(
        canonical_id=str(listing.canonical_id),
        address_normalized=listing.address_normalized,
        price_cad=listing.price_cad,
        bedrooms=listing.bedrooms,
        phash=listing.phash,
    )


def _to_candidate_from_row(row: Listing) -> Candidate:
    return Candidate(
        canonical_id=row.canonical_id or row.id,
        address_normalized=row.address_normalized,
        price_cad=row.price_cad,
        bedrooms=row.bedrooms,
        phash=row.phash,
    )


def _uuid_from_str(s: str) -> UUID:
    return UUID(s)
