"""Listing quality / scam-signal heuristics.

Issue #120 — every listing gets up to N small flags. Each flag is a
pure function of (the listing, the in-memory listing pool) — no LLM,
no external data, no DB lookup. That makes them testable, explainable
to the user, and impossible to silently break.

Flags ship today:

- ``price_outlier_low`` — listing's price is > 2 standard deviations
  below the median for listings with the same bedroom count *in the
  same source*. The "same source" scoping matters: cross-source
  comparisons mix sale prices (REW) with rentals, which would fire
  every rental row as an outlier.
- ``missing_essentials`` — ``address`` is null AND at least one of
  (``photos``, ``description_snippet``) is also null. Address is the
  discriminator: real landlords post one; scam listings hide it.
  Pairing it with a second missing field rules out the common "real
  listing that happens to be missing one field" case.
- ``duplicate_contact`` — the listing's contact phone or email
  (extracted from ``raw_metadata``) appears in N≥3 other listings in
  the same response. Real landlords post a few units; scam rings
  post the same contact dozens of times.
- ``photo_phash_collision`` — the listing's ``phash`` is within
  Hamming distance 4 of a listing from a *different source* whose
  ``canonical_id`` differs. Already-canonical-merged dupes are by
  definition the same unit and don't fire this. A separate canonical
  cluster with the same photos is what we're surfacing.
- ``terse_no_address`` — ``description_snippet`` is shorter than 30
  chars AND ``address`` is null. A real listing has at least one of
  the two.

The aggregator computes a :class:`QualityContext` once per request
(medians, contact counter, phash index) and runs :func:`compute_flags`
per listing against it. The result lands on
``NormalizedListing.quality_flags`` in the response.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from rentwise.models import NormalizedListing


class QualityFlag(StrEnum):
    """Stable wire-format names — see this file's module docstring."""

    PRICE_OUTLIER_LOW = "price_outlier_low"
    MISSING_ESSENTIALS = "missing_essentials"
    DUPLICATE_CONTACT = "duplicate_contact"
    PHOTO_PHASH_COLLISION = "photo_phash_collision"
    TERSE_NO_ADDRESS = "terse_no_address"


# Detail strings the frontend renders in the chip popover. Keep short
# and user-readable — these are NOT log messages.
FLAG_LABELS: dict[QualityFlag, str] = {
    QualityFlag.PRICE_OUTLIER_LOW: "Suspiciously cheap",
    QualityFlag.MISSING_ESSENTIALS: "Missing key details",
    QualityFlag.DUPLICATE_CONTACT: "Same contact as other listings",
    QualityFlag.PHOTO_PHASH_COLLISION: "Photos seen on another listing",
    QualityFlag.TERSE_NO_ADDRESS: "Very thin description",
}


@dataclass
class QualityContext:
    """Per-request statistics needed to evaluate cross-listing flags.

    Built once by :func:`build_context` from the in-memory listing
    pool, then passed to :func:`compute_flags` for each listing.
    """

    # (source, bedrooms_bucket) -> median price among listings with
    # a numeric price_cad. Sample size also kept so we can skip
    # flagging when the bucket is too small to be statistically
    # meaningful.
    medians_by_bucket: dict[tuple[str, float | None], float] = field(default_factory=dict)
    stdevs_by_bucket: dict[tuple[str, float | None], float] = field(default_factory=dict)
    sample_sizes: dict[tuple[str, float | None], int] = field(default_factory=dict)

    # Contact-string -> set of listing ids that carry it. Lets us
    # both decide the flag AND tell the user how many other rows.
    contact_index: dict[str, set[str]] = field(default_factory=dict)

    # phash (hex) -> set of canonical_ids that carry it. We check for
    # collisions where canonical_ids differ → different units sharing
    # the same photo.
    phash_canonical_index: dict[str, set[str]] = field(default_factory=dict)


# ---------- context building ----------

_PHONE_RE = re.compile(r"(?:\+?\d[\s\-.()]?){10,}")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _bucket_for(listing: NormalizedListing) -> tuple[str, float | None]:
    """Bucket key for price-outlier comparisons: (source, rounded bedrooms)."""
    beds = listing.bedrooms
    if beds is None:
        return (listing.source, None)
    # 0.5 bucket — group studios separately from 1BRs; 1.5BRs land with 1BR.
    return (listing.source, round(beds * 2) / 2)


def _extract_contact_strings(listing: NormalizedListing) -> list[str]:
    """Best-effort phone + email extraction from ``raw_metadata`` and snippet.

    Returns normalized strings (digits-only for phones, lowercase for emails).
    Empty list if nothing parseable was found.
    """
    out: list[str] = []
    raw: dict[str, Any] = listing.raw_metadata or {}
    fields_to_scan = [
        raw.get("contact_phone"),
        raw.get("phone"),
        raw.get("contact_email"),
        raw.get("email"),
        listing.description_snippet,
    ]
    for v in fields_to_scan:
        if not isinstance(v, str):
            continue
        for m in _PHONE_RE.finditer(v):
            digits = re.sub(r"\D", "", m.group(0))
            if len(digits) >= 10:
                # Last 10 digits is enough — strips +1, area-code parens, etc.
                out.append(digits[-10:])
        for m in _EMAIL_RE.finditer(v):
            out.append(m.group(0).casefold())
    return out


def build_context(listings: list[NormalizedListing]) -> QualityContext:
    """Aggregate the cross-listing stats needed for flag evaluation."""
    ctx = QualityContext()

    # Group prices per (source, bedrooms_bucket).
    grouped: dict[tuple[str, float | None], list[int]] = {}
    for listing in listings:
        if listing.price_cad is None:
            continue
        grouped.setdefault(_bucket_for(listing), []).append(listing.price_cad)
    for bucket, prices in grouped.items():
        ctx.sample_sizes[bucket] = len(prices)
        if len(prices) >= 3:
            ctx.medians_by_bucket[bucket] = statistics.median(prices)
            ctx.stdevs_by_bucket[bucket] = statistics.pstdev(prices) if len(prices) >= 2 else 0.0

    # Index contacts.
    for listing in listings:
        for contact in _extract_contact_strings(listing):
            ctx.contact_index.setdefault(contact, set()).add(str(listing.id))

    # Index phashes.
    for listing in listings:
        if not listing.phash:
            continue
        ctx.phash_canonical_index.setdefault(listing.phash, set()).add(str(listing.canonical_id))

    return ctx


# ---------- per-listing evaluation ----------


def _is_price_outlier_low(listing: NormalizedListing, ctx: QualityContext) -> bool:
    if listing.price_cad is None:
        return False
    bucket = _bucket_for(listing)
    sample = ctx.sample_sizes.get(bucket, 0)
    if sample < 3:
        return False
    median = ctx.medians_by_bucket.get(bucket)
    stdev = ctx.stdevs_by_bucket.get(bucket)
    if median is None or stdev is None or stdev == 0:
        return False
    # > 2 sigma below median.
    return listing.price_cad < (median - 2 * stdev)


def _has_missing_essentials(listing: NormalizedListing) -> bool:
    # Address missing is the strong signal; pair with at least one
    # secondary miss so a legit "address-anonymized for showing" doesn't
    # fire on its own.
    if listing.address:
        return False
    return not listing.photos or not listing.description_snippet


def _has_duplicate_contact(listing: NormalizedListing, ctx: QualityContext) -> bool:
    contacts = _extract_contact_strings(listing)
    if not contacts:
        return False
    for c in contacts:
        ids = ctx.contact_index.get(c, set())
        # >= 3 distinct listings sharing this contact — this listing
        # being one of them. So we want |ids| >= 3.
        if len(ids) >= 3:
            return True
    return False


def _has_photo_phash_collision(listing: NormalizedListing, ctx: QualityContext) -> bool:
    if not listing.phash:
        return False
    canonical_ids = ctx.phash_canonical_index.get(listing.phash, set())
    # Same canonical_id == already dedup'd as the same unit; that's a
    # signal we WANT, not a quality concern.
    return any(cid != str(listing.canonical_id) for cid in canonical_ids)


def _is_terse_no_address(listing: NormalizedListing) -> bool:
    snippet_len = len(listing.description_snippet or "")
    return snippet_len < 30 and not listing.address


def compute_flags(listing: NormalizedListing, ctx: QualityContext) -> list[QualityFlag]:
    """Return all quality flags that fire for ``listing`` in this context."""
    out: list[QualityFlag] = []
    if _is_price_outlier_low(listing, ctx):
        out.append(QualityFlag.PRICE_OUTLIER_LOW)
    if _has_missing_essentials(listing):
        out.append(QualityFlag.MISSING_ESSENTIALS)
    if _has_duplicate_contact(listing, ctx):
        out.append(QualityFlag.DUPLICATE_CONTACT)
    if _has_photo_phash_collision(listing, ctx):
        out.append(QualityFlag.PHOTO_PHASH_COLLISION)
    if _is_terse_no_address(listing):
        out.append(QualityFlag.TERSE_NO_ADDRESS)
    return out
