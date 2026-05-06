"""feedparser entry → RawListing."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import HttpUrl

from rentwise.adapters.craigslist.title_parser import parse_title
from rentwise.models import RawListing

log = structlog.get_logger(__name__)

_ID_RE = re.compile(r"/(\d{6,})\.html$")


def _post_id(url: str) -> str | None:
    m = _ID_RE.search(url)
    return m.group(1) if m else None


def _truncate_snippet(text: str | None, max_len: int = 200) -> str | None:
    if not text:
        return None
    text = text.strip()
    return text[:max_len]


def parse_entry(entry: Any) -> RawListing | None:
    link = getattr(entry, "link", None)
    if not link:
        return None
    post_id = _post_id(link)
    if not post_id:
        return None

    title = getattr(entry, "title", "") or ""
    parsed_title = parse_title(title)

    posted_at_str = (
        getattr(entry, "dc_date", None)
        or getattr(entry, "updated", None)
        or getattr(entry, "published", None)
    )
    try:
        posted_at = datetime.fromisoformat(posted_at_str) if posted_at_str else datetime.now(UTC)
    except (TypeError, ValueError):
        posted_at = datetime.now(UTC)

    lat = getattr(entry, "geo_lat", None)
    lon = getattr(entry, "geo_long", None)
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        lat = None
        lon = None

    snippet = _truncate_snippet(getattr(entry, "summary", None))

    try:
        return RawListing(
            source="craigslist",
            source_url=HttpUrl(link),
            source_listing_id=post_id,
            title=title,
            address=None,
            lat=lat,
            lon=lon,
            bedrooms=parsed_title.bedrooms,
            bathrooms=None,
            price_cad=parsed_title.price_cad,
            pets_allowed=None,
            furnished=None,
            available_date=None,
            posted_at=posted_at,
            photos=[],
            description_snippet=snippet,
            raw_metadata={
                "neighborhood_hint": parsed_title.neighborhood_hint,
                "sqft_hint": parsed_title.sqft,
            },
        )
    except Exception as exc:
        log.warning("rss.parse_failed", post_id=post_id, error=str(exc))
        return None
