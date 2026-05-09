"""Rentals.ca direct adapter (Phase 8 PR-C scaffold).

Status
------
This is a SCAFFOLD. The site is client-side rendered and our single
exploratory fetch returned HTTP 403 to the project User-Agent, so the
selectors below have NOT been calibrated against the live rendered DOM.
`_extract` makes a best-effort attempt against conservative selectors that
match the synthetic test fixture; if nothing matches, it logs a warning and
returns an empty list. **Do not enable in production until selectors are
re-calibrated by manually inspecting a rendered page.**

Operational rules (see `docs/operational-rules.md`)
---------------------------------------------------
- robots.txt is checked at search time before each fetch. Disallowed paths
  abort and `health_check` reports `status="blocked"`.
- Rate limit: 0.5 req/sec (well under the 1.0 ceiling), 500-1500 ms jitter.
- Identifying User-Agent (no Chrome impersonation).
- Avoids robots.txt-disallowed query params (bbox, amenities, types,
  *-feed.json, *-feed.xml).
- Snippets truncated to <= 200 chars before returning.
- Disabled by default at registration via RENTWISE_RENTALSCA_ENABLED.

TOS reality
-----------
Rentals.ca TOS § 3.16 explicitly prohibits automated extraction. This
adapter is a deliberate personal-use opt-in; opt-in is per-source via
the env var. If the site asks us to stop (consecutive 403/429), the
adapter reports blocked and the aggregator skips it.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import ClassVar, Literal
from urllib.parse import urlencode

import httpx
import structlog
from pydantic import HttpUrl, ValidationError

from rentwise.adapters.base import (
    AdapterCapabilities,
    RobotsDisallowedError,
    SourceAdapter,
)
from rentwise.adapters.playwright_fetcher import PlaywrightFetcher
from rentwise.adapters.robots import RobotsCache
from rentwise.models import AdapterHealth, NormalizedQuery, RawListing

log = structlog.get_logger(__name__)

_BASE_URL = "https://rentals.ca"
_SEARCH_PATH = "/vancouver"

# robots.txt-disallowed query params we must NEVER include.
_DISALLOWED_PARAMS: frozenset[str] = frozenset({"bbox", "amenities", "types"})

# Conservative selector hints used by the synthetic fixture parser.
# These are NOT calibrated against live rentals.ca markup.
_LISTING_CARD_TAG = "article"
_LISTING_CARD_ATTR = ("data-testid", "listing-card")


class _ListingCardParser(HTMLParser):
    """Best-effort listing card parser.

    Walks the DOM looking for `<article data-testid="listing-card">` blocks
    (the structure our synthetic fixture exercises) and pulls out the link,
    title, address, price, bedrooms, photo URL, and description snippet.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[dict[str, str]] = []
        self._in_card = False
        self._card_depth = 0
        self._current: dict[str, str] = {}
        # Track which "field" tag we're currently capturing text into.
        self._capture_field: str | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k: (v or "") for k, v in attrs}

        if (
            not self._in_card
            and tag == _LISTING_CARD_TAG
            and attr_map.get(_LISTING_CARD_ATTR[0]) == _LISTING_CARD_ATTR[1]
        ):
            self._in_card = True
            self._card_depth = 1
            self._current = {}
            listing_id = attr_map.get("data-listing-id", "")
            if listing_id:
                self._current["listing_id"] = listing_id
            return

        if not self._in_card:
            return

        # Track nested depth so we know when this card ends.
        if tag == _LISTING_CARD_TAG:
            self._card_depth += 1

        # Anchor tag with class "listing-link" gives us the URL + listing id.
        if tag == "a" and "listing-link" in attr_map.get("class", "").split():
            href = attr_map.get("href", "")
            if href and "url" not in self._current:
                self._current["url"] = href

        # data-field="title|address|price|bedrooms|snippet" → capture text.
        field = attr_map.get("data-field")
        if field and self._capture_field is None:
            self._capture_field = field
            self._buffer = []

        # Photo URL from <img src=...>
        if tag == "img" and "photo" not in self._current:
            src = attr_map.get("src", "")
            if src:
                self._current["photo"] = src

    def handle_endtag(self, tag: str) -> None:
        if not self._in_card:
            return

        if self._capture_field is not None:
            # Field tags are non-nesting in our fixture; close on any end tag
            # while we're capturing.
            text = "".join(self._buffer).strip()
            if text:
                self._current[self._capture_field] = text
            self._capture_field = None
            self._buffer = []

        if tag == _LISTING_CARD_TAG:
            self._card_depth -= 1
            if self._card_depth <= 0:
                if self._current:
                    self.cards.append(self._current)
                self._in_card = False
                self._card_depth = 0
                self._current = {}

    def handle_data(self, data: str) -> None:
        if self._in_card and self._capture_field is not None:
            self._buffer.append(data)


def _truncate_snippet(text: str | None, max_len: int = 200) -> str | None:
    if not text:
        return None
    text = text.strip()
    if len(text) > max_len:
        return text[:max_len]
    return text


_PRICE_RE = re.compile(r"[\d,]+")
_BEDS_RE = re.compile(r"(\d+(?:\.\d+)?)")


def _parse_price(text: str | None) -> int | None:
    if not text:
        return None
    m = _PRICE_RE.search(text)
    if not m:
        return None
    try:
        return int(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _parse_bedrooms(text: str | None) -> float | None:
    if not text:
        return None
    if "studio" in text.lower() or "bachelor" in text.lower():
        return 0.5
    m = _BEDS_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _absolute_url(url: str) -> str:
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("/"):
        return f"{_BASE_URL}{url}"
    return f"{_BASE_URL}/{url}"


def _build_search_url(query: NormalizedQuery) -> str:
    """Build a robots.txt-safe search URL.

    Avoids `bbox=`, `amenities=`, `types=`, and feed paths.
    """
    params: dict[str, str] = {}
    if query.price_min is not None:
        params["min_price"] = str(query.price_min)
    if query.price_max is not None:
        params["max_price"] = str(query.price_max)
    if query.bedrooms_min is not None:
        params["beds_min"] = str(int(query.bedrooms_min))
    if query.bedrooms_max is not None:
        params["beds_max"] = str(int(query.bedrooms_max))

    # Defensive: drop any disallowed param if it ever sneaks in.
    safe_params = {k: v for k, v in params.items() if k not in _DISALLOWED_PARAMS}
    qs = urlencode(safe_params)
    base = f"{_BASE_URL}{_SEARCH_PATH}"
    return f"{base}?{qs}" if qs else base


class RentalsCaAdapter:
    """Rentals.ca scaffold adapter — see module docstring for status."""

    name: str = "rentals_ca"
    base_url: str = _BASE_URL
    method: Literal["api", "rss", "browser"] = "browser"
    rate_limit_per_second: float = 0.5
    # Scaffold flag (#94). Selectors only match the synthetic test
    # fixture — live rentals.ca returns 403 to our UA via Cloudflare,
    # so the parser hasn't been confirmed against rendered HTML.
    is_extractor_calibrated: bool = False

    _capabilities: ClassVar[AdapterCapabilities] = {
        "supported_filters": {
            "bedrooms_min",
            "bedrooms_max",
            "price_min",
            "price_max",
        }
    }

    def __init__(
        self,
        *,
        user_agent: str,
        fetcher: PlaywrightFetcher | None = None,
        robots: RobotsCache | None = None,
        jitter_ms: tuple[int, int] = (500, 1500),
    ) -> None:
        self.user_agent = user_agent
        self.capabilities: AdapterCapabilities = self._capabilities
        # Lazily owned fetcher; tests inject a fake.
        self._fetcher: PlaywrightFetcher | None = fetcher
        self._owns_fetcher = fetcher is None
        # `robots` is shared between health_check (HEAD-style probe) and the
        # PlaywrightFetcher's own robots check. Tests can swap it.
        self.robots = robots or RobotsCache(user_agent=user_agent)
        self._jitter_ms = jitter_ms

    def _get_fetcher(self) -> PlaywrightFetcher:
        if self._fetcher is None:
            self._fetcher = PlaywrightFetcher(
                user_agent=self.user_agent,
                rate_per_sec=self.rate_limit_per_second,
                jitter_ms=self._jitter_ms,
            )
            # Share the robots cache so repeated checks aren't duplicated.
            self._fetcher.robots = self.robots
        return self._fetcher

    def _extract(self, html: str) -> list[RawListing]:
        """Parse rendered HTML into RawListings.

        SCAFFOLD: selectors are calibrated against the synthetic test
        fixture, NOT against live rentals.ca markup. If nothing matches,
        we log a warning and return [] rather than guess.
        """
        parser = _ListingCardParser()
        try:
            parser.feed(html)
        except Exception as exc:
            log.warning("rentalsca.parse_failed", error=str(exc))
            return []

        if not parser.cards:
            log.warning(
                "rentalsca.selectors_not_yet_calibrated",
                hint=(
                    "no listing cards matched the scaffold selectors; "
                    "calibrate against a live rendered page before enabling "
                    "RENTWISE_RENTALSCA_ENABLED in production"
                ),
            )
            return []

        listings: list[RawListing] = []
        now = datetime.now(UTC)
        for card in parser.cards:
            url = _absolute_url(card.get("url", ""))
            listing_id = card.get("listing_id") or url.rsplit("/", 1)[-1] or url
            title = card.get("title") or "Rentals.ca listing"
            price = _parse_price(card.get("price"))
            bedrooms = _parse_bedrooms(card.get("bedrooms"))
            address = card.get("address") or None
            photo = card.get("photo")
            snippet = _truncate_snippet(card.get("snippet"))
            try:
                photos: list[HttpUrl] = []
                if photo:
                    photos.append(HttpUrl(_absolute_url(photo)))
                listings.append(
                    RawListing(
                        source=self.name,
                        source_url=HttpUrl(url),
                        source_listing_id=listing_id,
                        title=title,
                        address=address,
                        bedrooms=bedrooms,
                        price_cad=price,
                        posted_at=now,
                        photos=photos,
                        description_snippet=snippet,
                    )
                )
            except ValidationError as exc:
                log.warning(
                    "rentalsca.listing_skipped",
                    listing_id=listing_id,
                    error=str(exc),
                )
                continue
        return listings

    async def search(self, query: NormalizedQuery) -> AsyncIterator[RawListing]:
        url = _build_search_url(query)

        # Honor robots.txt at the adapter boundary too — defense in depth.
        if not await self.robots.is_allowed(url):
            log.warning("rentalsca.robots_disallowed", url=url)
            return

        fetcher = self._get_fetcher()
        attr_name, attr_value = _LISTING_CARD_ATTR
        wait_selector = f'{_LISTING_CARD_TAG}[{attr_name}="{attr_value}"]'
        try:
            html = await fetcher.fetch_html(url, wait_for=wait_selector)
        except RobotsDisallowedError:
            log.warning("rentalsca.robots_disallowed", url=url)
            return
        except Exception as exc:
            log.warning("rentalsca.fetch_failed", url=url, error=str(exc))
            return

        for listing in self._extract(html):
            yield listing

    async def fetch_listing(self, listing_id: str) -> RawListing | None:
        # Per-listing fetch not implemented while selectors remain uncalibrated.
        return None

    async def health_check(self) -> AdapterHealth:
        """Lightweight check: robots.txt + a HEAD/GET against the search page.

        Reports `blocked` on robots disallow OR consecutive 403/429.
        Does NOT spin up Playwright — uses httpx so health is cheap.
        """
        url = f"{_BASE_URL}{_SEARCH_PATH}"
        try:
            if not await self.robots.is_allowed(url):
                return AdapterHealth(name=self.name, status="blocked", last_error="robots.txt")
            async with httpx.AsyncClient(headers={"User-Agent": self.user_agent}) as client:
                resp = await client.get(url, timeout=5)
            if resp.status_code in (403, 429):
                return AdapterHealth(
                    name=self.name,
                    status="blocked",
                    last_error=f"HTTP {resp.status_code}",
                )
            if resp.status_code != 200:
                return AdapterHealth(
                    name=self.name,
                    status="degraded",
                    last_error=f"HTTP {resp.status_code}",
                )
            return AdapterHealth(name=self.name, status="ok")
        except httpx.HTTPError as exc:
            return AdapterHealth(name=self.name, status="degraded", last_error=str(exc))

    async def close(self) -> None:
        """Idempotent shutdown of the underlying fetcher (if we own it)."""
        if self._fetcher is not None and self._owns_fetcher:
            await self._fetcher.close()
            self._fetcher = None


# Type assertion: instances satisfy the Protocol.
_: SourceAdapter = RentalsCaAdapter(user_agent="RentWise/0.1")
