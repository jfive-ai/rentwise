"""/jsonsearch/apa entry → RawListing.

Replaces rss_parser.py because Craigslist now returns 403 for the RSS feed
even from residential IPs (verified 2026-05-08), but `/jsonsearch/apa`
serves a richer JSON payload from the same network. See
docs/operational-rules.md "Source notes — Craigslist" for the rationale.

Schema we depend on (per real samples):
    {
      "PostingID":     int,
      "PostingURL":    str,
      "PostingTitle":  str,
      "PostedDate":    int (unix seconds),
      "Latitude":      float | null,
      "Longitude":     float | null,
      "bedrooms":      int | null,
      "price":         int | null,
      "ImageThumb":    str | null,
      "CategoryID":    int,
      ...
    }

Anything missing → field is `None`. Adversarial / partial entries don't
raise — they map to `None` and the caller decides whether to keep them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import HttpUrl

from rentwise.adapters.craigslist.title_parser import parse_title
from rentwise.models import RawListing

log = structlog.get_logger(__name__)


def _truncate_snippet(text: str | None, max_len: int = 200) -> str | None:
    if not text:
        return None
    text = text.strip()
    return text[:max_len]


def _coerce_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _coerce_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def parse_entry(entry: Any) -> RawListing | None:
    """Translate one /jsonsearch/apa item into a RawListing.

    Returns None when the entry is missing the bare-minimum fields
    (URL or postingID) — those rows wouldn't be addressable downstream.
    """
    if not isinstance(entry, dict):
        return None

    url = entry.get("PostingURL")
    post_id = entry.get("PostingID")
    if not url or post_id is None:
        return None

    title = entry.get("PostingTitle") or ""

    posted_ts = _coerce_int(entry.get("PostedDate"))
    try:
        posted_at = datetime.fromtimestamp(posted_ts, tz=UTC) if posted_ts else datetime.now(UTC)
    except (OSError, OverflowError, ValueError):
        # Future / out-of-range timestamps from a misbehaving API: don't
        # let them crash the whole search.
        posted_at = datetime.now(UTC)

    lat = _coerce_float(entry.get("Latitude"))
    lon = _coerce_float(entry.get("Longitude"))

    # Prefer the structured `bedrooms` / `price` fields over the regex-
    # parsed ones, but keep the title parser around for the
    # neighborhood + sqft hints (the JSON doesn't carry those).
    structured_beds = _coerce_float(entry.get("bedrooms"))
    structured_price = _coerce_int(entry.get("price"))
    title_hints = parse_title(title)

    bedrooms = structured_beds if structured_beds is not None else title_hints.bedrooms
    price = structured_price if structured_price is not None else title_hints.price_cad

    snippet = _truncate_snippet(entry.get("PostingTitle"))

    try:
        return RawListing(
            source="craigslist",
            source_url=HttpUrl(str(url)),
            source_listing_id=str(post_id),
            title=title,
            address=None,
            lat=lat,
            lon=lon,
            bedrooms=bedrooms,
            bathrooms=None,
            price_cad=price,
            pets_allowed=None,
            furnished=None,
            available_date=None,
            posted_at=posted_at,
            photos=[],
            description_snippet=snippet,
            raw_metadata={
                "neighborhood_hint": title_hints.neighborhood_hint,
                "sqft_hint": title_hints.sqft,
                "image_thumb_url": entry.get("ImageThumb"),
            },
        )
    except Exception as exc:
        log.warning("craigslist.json.parse_failed", post_id=post_id, error=str(exc))
        return None
