"""liv.rent Vancouver direct adapter — calibrated against live HTML (#105).

Pulls listings off the city-scoped landing page
(``https://liv.rent/rental-listings/city/vancouver``). The page is a Next.js
SPA that hydrates listing cards client-side; the shared ``PlaywrightFetcher``
waits on a detail-anchor selector before snapshotting HTML.

Each card is a wrapping ``<a target="_blank" rel="opener" href="/rental-listings/detail/...">``
that contains:

- a child ``<div data-impression-listingid="<id>" data-impression-section="listing-card">``
- one or more ``<img>`` whose ``src`` is a Next.js image-proxy URL pointing at
  ``cdn.liv.rent/static_files/unit/...``
- text fragments rendered by stylized divs/spans:
  ``["Top Choice"|"Popular"|"Special Offer", "$3,000", "/month",
    "2 Bed · 1 Bath · 675 ft²", "<street>", "<city>, BC · <unit type>",
    "Check Availability"]``

We extract listing id, photo URL, price, bedrooms, bathrooms, address (street
joined with ``city, BC``), and synthesize a title from the URL path. We do NOT
re-host photos — only the canonical CDN URL is stored.

Operational rules — see ``docs/operational-rules.md``:

- robots.txt is checked at fetch time via ``PlaywrightFetcher.robots``.
- 0.5 req/sec (half the platform-wide ceiling), 500-1500 ms jitter.
- Identifying User-Agent ("RentWise/...").
- ``description_snippet`` capped at 200 chars.

TOS reality (carry-over from the scaffold note): liv.rent § 7.1(v)/(w)
prohibits scraping/indexing/data-mining and bot use. We honor the
single-user / personal-use rationale documented in ``docs/operational-rules.md``;
the adapter is opt-in via ``RENTWISE_LIVRENT_ENABLED``.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import ClassVar
from urllib.parse import unquote

import structlog
from pydantic import HttpUrl, ValidationError

from rentwise.adapters.base import AdapterCapabilities
from rentwise.adapters.scaffold_base import ScaffoldAdapterBase
from rentwise.models import NormalizedQuery, RawListing

log = structlog.get_logger(__name__)

# A wrapping anchor up to (but not including) the next listing anchor or the
# end of the listings region. Robust to small DOM changes inside the card.
_LISTING_ANCHOR_RE = re.compile(
    r'<a[^>]*href="(?P<href>/rental-listings/detail/[^"]+)"[^>]*>'
    r"(?P<inner>.*?)"
    r'(?=<a[^>]*href="/rental-listings/detail/|</main>|</section>)',
    re.DOTALL,
)

_LISTING_ID_RE = re.compile(r'data-impression-listingid="(\d+)"')
# Promo overlays in liv.rent cards (e.g. "$50 first-month off") are always
# strictly smaller than the rent — picking max($-amounts) is robust to layout
# order without depending on per-card variants.
_PRICE_RE = re.compile(r"\$([\d,]+)")
_BEDS_RE = re.compile(r"(\d+(?:\.\d+)?|Studio)\s*Bed", re.IGNORECASE)
_BATHS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*Bath", re.IGNORECASE)
# Card text uses "<city>, BC · <unit type>" (with U+00B7). The street fragment
# is the one immediately before the city/BC fragment.
_CITY_BC_RE = re.compile(r"^([\w .'-]+),\s*BC")
# Promo / decorator chips that show up as standalone text fragments and are
# never part of the address.
_PROMO_FRAGMENTS = frozenset(
    {
        "Top Choice",
        "Popular",
        "Special Offer",
        "Verified",
        "New Listing",
        "Featured",
        "/month",
        "Check Availability",
        "Add to Favourites",
    }
)
# liv.rent serves images via a Next.js proxy: /_next/image?url=<encoded-cdn-url>...
_NEXT_IMAGE_URL_RE = re.compile(r"<img[^>]+src=\"(/_next/image\?url=[^\"]+)\"")
_PLAIN_IMG_SRC_RE = re.compile(r"<img[^>]+src=\"(https?://[^\"]+)\"")
_NEXT_IMAGE_INNER_RE = re.compile(r"url=([^&]+)")


def _strip_html_to_fragments(html_block: str) -> list[str]:
    """Reduce a card's HTML into the list of visible text fragments.

    Drops <img> tags first (their alt text would otherwise leak into the
    fragment list and dominate the address heuristic), then converts every
    remaining tag into a separator and collapses runs of separators.
    """
    no_img = re.sub(r"<img[^>]*/?>", "", html_block)
    text = re.sub(r"<[^>]+>", "|", no_img)
    text = re.sub(r"\|+", "|", text)
    return [p.strip() for p in text.split("|") if p.strip()]


def _first_photo_url(html_block: str) -> str | None:
    """Decode the first liv.rent CDN image URL from a Next.js proxy ``src``.

    Falls back to the first plain absolute ``src`` if the proxy form isn't
    present (defensive — the page currently always uses the proxy form).
    """
    proxy = _NEXT_IMAGE_URL_RE.search(html_block)
    if proxy is not None:
        inner = _NEXT_IMAGE_INNER_RE.search(proxy.group(1))
        if inner is not None:
            return unquote(inner.group(1))
        return proxy.group(1)
    plain = _PLAIN_IMG_SRC_RE.search(html_block)
    return plain.group(1) if plain is not None else None


def _max_price(fragments: list[str]) -> int | None:
    found: list[int] = []
    for f in fragments:
        for m in _PRICE_RE.finditer(f):
            try:
                found.append(int(m.group(1).replace(",", "")))
            except ValueError:
                continue
    return max(found) if found else None


def _beds_baths(fragments: list[str]) -> tuple[float | None, float | None]:
    bedrooms: float | None = None
    bathrooms: float | None = None
    for f in fragments:
        if bedrooms is None:
            bm = _BEDS_RE.search(f)
            if bm is not None:
                tok = bm.group(1)
                bedrooms = 0.5 if tok.lower() == "studio" else float(tok)
        if bathrooms is None:
            am = _BATHS_RE.search(f)
            if am is not None:
                bathrooms = float(am.group(1))
        if bedrooms is not None and bathrooms is not None:
            return bedrooms, bathrooms
    return bedrooms, bathrooms


def _address_from_fragments(fragments: list[str]) -> str | None:
    """Return ``"<street>, <city>, BC"`` if both fragments are present.

    The "<city>, BC · <unit type>" fragment is the anchor: we walk fragments
    in order, take the first one that starts with that pattern, and treat the
    most recent non-promo / non-numeric fragment before it as the street.
    """
    street: str | None = None
    for f in fragments:
        m = _CITY_BC_RE.match(f)
        if m is not None:
            city_bc = f"{m.group(1).strip()}, BC"
            if street is None:
                return city_bc
            return f"{street}, {city_bc}"
        if f in _PROMO_FRAGMENTS or f.startswith("$") or _BEDS_RE.search(f) or _BATHS_RE.search(f):
            continue
        street = f
    return street


def _title_from_href(
    href: str,
    bedrooms: float | None,
    address: str | None,
) -> str:
    """Synthesize a card title from the URL path + counts.

    liv.rent doesn't render a per-card title on the landing page — the
    detail page does. Compose ``"<beds>BR <type> — <street/city>"`` so the
    listing has a useful display string without a follow-up fetch.
    """
    parts = href.split("/")
    housing_type = parts[3] if len(parts) > 3 else "rental"
    if bedrooms == 0.5:
        beds_str = "Studio"
    elif bedrooms is not None:
        beds_str = f"{int(bedrooms)}BR"
    else:
        beds_str = "Rental"
    where = address or housing_type.title()
    return f"{beds_str} {housing_type} — {where}".strip()


def _parse_card(href: str, inner_html: str) -> RawListing | None:
    """Build a ``RawListing`` from one card's HTML, or ``None`` on failure.

    Never raises — the aggregator counts non-yields as the signal for
    "scaffold not calibrated", so a live-DOM drift surfaces as one missing
    card, not a 500.
    """
    lid_m = _LISTING_ID_RE.search(inner_html)
    if lid_m is None:
        return None
    listing_id = lid_m.group(1)

    fragments = _strip_html_to_fragments(inner_html)
    price = _max_price(fragments)
    bedrooms, bathrooms = _beds_baths(fragments)
    address = _address_from_fragments(fragments)
    photo = _first_photo_url(inner_html)
    title = _title_from_href(href, bedrooms, address)

    full_url = f"https://liv.rent{href}"
    photos: list[HttpUrl] = []
    if photo:
        try:
            photos.append(HttpUrl(photo))
        except ValidationError:
            pass

    try:
        return RawListing(
            source="livrent",
            source_url=HttpUrl(full_url),
            source_listing_id=listing_id,
            title=title,
            address=address,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            price_cad=price,
            posted_at=datetime.now(UTC),
            photos=photos,
            description_snippet=None,
        )
    except ValidationError as exc:
        log.warning("livrent.listing_skipped", listing_id=listing_id, error=str(exc))
        return None


class LivRentAdapter(ScaffoldAdapterBase):
    name: str = "livrent"
    base_url: str = "https://liv.rent"
    is_extractor_calibrated: bool = True
    _capabilities: ClassVar[AdapterCapabilities] = {
        # The landing page doesn't honor URL filter params; the aggregator
        # post-filters by price/beds/etc. (same as Craigslist).
        "supported_filters": set(),
    }

    def _search_url(self, query: NormalizedQuery) -> str:
        return f"{self.base_url}/rental-listings/city/vancouver"

    def _wait_for(self) -> str | None:
        # Listing cards anchor to /rental-listings/detail/<type>/<city>/<id>.
        return 'a[href*="/rental-listings/detail/"]'

    def _extract(self, html: str, query: NormalizedQuery) -> list[RawListing]:
        out: list[RawListing] = []
        for m in _LISTING_ANCHOR_RE.finditer(html):
            listing = _parse_card(m.group("href"), m.group("inner"))
            if listing is not None:
                out.append(listing)
        if not out:
            log.warning(
                "livrent.no_listings_extracted",
                hint=(
                    "live DOM may have drifted; recapture the fixture and "
                    "verify _LISTING_ANCHOR_RE / _CITY_BC_RE still match"
                ),
            )
        return out
