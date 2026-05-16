"""Fixture-backed demo adapter.

Loads pre-recorded listings for a single source and yields them through the
SourceAdapter contract. Used when ``RENTWISE_DEMO_MODE=true`` so the full
search pipeline (aggregator → enrichment → dedup → API → UI) can run in
sandboxed environments where the live sites are unreachable (CI, ephemeral
containers, offline development).

Demo mode is **off by default**. When on, ``_build_adapters`` registers one
``FixtureAdapter`` per supported source instead of the live network adapter
for that source. The fixtures used here are the same ones the unit tests
exercise — synthetic data, no verbatim long descriptions, no re-hosted
photos. See ``docs/operational-rules.md``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import ClassVar, Literal

import structlog

from rentwise.adapters.base import AdapterCapabilities, SourceAdapter
from rentwise.adapters.craigslist.json_parser import parse_entry as _cl_parse
from rentwise.adapters.livrent.adapter import LivRentAdapter
from rentwise.adapters.rentalsca.adapter import RentalsCaAdapter
from rentwise.models import AdapterHealth, NormalizedQuery, RawListing

log = structlog.get_logger(__name__)

_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
_ADAPTER_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "adapters"


def _load_craigslist() -> list[RawListing]:
    path = _FIXTURES_DIR / "craigslist" / "sample_jsonsearch.json"
    payload = json.loads(path.read_text())
    entries = payload[0] if isinstance(payload[0], list) else []
    out: list[RawListing] = []
    for entry in entries:
        raw = _cl_parse(entry)
        if raw is not None:
            out.append(raw)
    return out


def _load_livrent() -> list[RawListing]:
    path = _ADAPTER_FIXTURES_DIR / "livrent" / "fixtures" / "search_page.html"
    html = path.read_text()
    adapter = LivRentAdapter(user_agent="RentWise-demo/0.1")
    return adapter._extract(html, NormalizedQuery())


def _load_rentalsca() -> list[RawListing]:
    path = _ADAPTER_FIXTURES_DIR / "rentalsca" / "fixtures" / "search_page.html"
    html = path.read_text()
    adapter = RentalsCaAdapter(user_agent="RentWise-demo/0.1")
    return adapter._extract(html)


def _load_synthetic_testid(source: str, fixture_dir: str, base_url: str) -> list[RawListing]:
    """Parse the data-testid synthetic fixture used by padmapper/zumper/rew.

    Structure (shared by all three):

        <article data-testid="listing-card">
          <a href="/path/to/listing-id">
            <h2>{title}</h2>
            <span data-testid="price">$1,959</span>
            <span data-testid="beds">Studio</span>
            <span data-testid="address">3583 Test St, Vancouver, BC V5R 5L9</span>
          </a>
        </article>
    """
    import re
    from datetime import UTC, datetime
    from html import unescape

    from pydantic import HttpUrl, ValidationError

    path = _ADAPTER_FIXTURES_DIR / fixture_dir / "fixtures" / "search_page.html"
    html = path.read_text()

    card_re = re.compile(
        r'<article[^>]*data-testid="listing-card"[^>]*>(?P<inner>.*?)</article>',
        re.DOTALL,
    )
    href_re = re.compile(r'<a[^>]*href="(?P<href>[^"]+)"')
    title_re = re.compile(r"<h2[^>]*>(?P<t>.*?)</h2>", re.DOTALL)
    price_re = re.compile(r'data-testid="price"[^>]*>(?P<p>[^<]+)<', re.DOTALL)
    beds_re = re.compile(r'data-testid="beds"[^>]*>(?P<b>[^<]+)<', re.DOTALL)
    addr_re = re.compile(r'data-testid="address"[^>]*>(?P<a>[^<]+)<', re.DOTALL)

    out: list[RawListing] = []
    now = datetime.now(UTC)
    for m in card_re.finditer(html):
        inner = m.group("inner")
        href_m = href_re.search(inner)
        if href_m is None:
            continue
        href = href_m.group("href")
        url = href if href.startswith("http") else f"{base_url}{href}"
        listing_id = href.rstrip("/").rsplit("/", 1)[-1]

        title_m = title_re.search(inner)
        title = unescape(title_m.group("t")).strip() if title_m else "Listing"

        price_m = price_re.search(inner)
        price = None
        if price_m:
            digits = re.sub(r"[^\d]", "", price_m.group("p"))
            if digits:
                price = int(digits)

        beds_m = beds_re.search(inner)
        bedrooms: float | None = None
        if beds_m:
            txt = beds_m.group("b").strip().lower()
            if "studio" in txt or "bachelor" in txt:
                bedrooms = 0.5
            else:
                num = re.search(r"\d+(?:\.\d+)?", txt)
                if num:
                    bedrooms = float(num.group(0))

        addr_m = addr_re.search(inner)
        address = unescape(addr_m.group("a")).strip() if addr_m else None

        try:
            out.append(
                RawListing(
                    source=source,
                    source_url=HttpUrl(url),
                    source_listing_id=listing_id,
                    title=title,
                    address=address,
                    bedrooms=bedrooms,
                    price_cad=price,
                    posted_at=now,
                )
            )
        except ValidationError as exc:
            log.warning("demo.fixture_listing_skipped", source=source, error=str(exc))
            continue
    return out


_LOADERS = {
    "craigslist": lambda: _load_craigslist(),
    "livrent": lambda: _load_livrent(),
    "rentals_ca": lambda: _load_rentalsca(),
    "padmapper": lambda: _load_synthetic_testid("padmapper", "padmapper", "https://padmapper.com"),
    "zumper": lambda: _load_synthetic_testid("zumper", "zumper", "https://www.zumper.com"),
    "rew": lambda: _load_synthetic_testid("rew", "rew", "https://www.rew.ca"),
}


_PRESET_CAPABILITIES: AdapterCapabilities = {
    # Declare the same filter set Craigslist supports so
    # `project_query_to_capabilities` does NOT strip price / bedroom /
    # keyword constraints before reaching `search()`. We apply them
    # ourselves below — without this, demo searches would return rows
    # that violate the user's filters (`price_max`, `bedrooms_*`, …),
    # which makes demo mode useless as an API/UI smoke test.
    "supported_filters": {
        "bedrooms_min",
        "bedrooms_max",
        "price_min",
        "price_max",
        "free_text_keywords",
    },
}


def _matches_query(raw: RawListing, query: NormalizedQuery) -> bool:
    """True iff this fixture row should be yielded for ``query``.

    Mirrors the obvious interpretations of each declared filter:

    - ``price_min`` / ``price_max``: rows with no ``price_cad`` are
      dropped when *either* bound is set (we can't confirm the row
      satisfies it, and silently returning unpriced rows past a
      ``price_max`` filter is the same kind of wrong this fix is
      preventing).
    - ``bedrooms_min`` / ``bedrooms_max``: same treatment — unknown
      bedroom counts are dropped when either bound is set.
    - ``free_text_keywords``: ALL keywords must appear as a casefold
      substring across the title + address + description_snippet
      (joined). Matches the "AND of keywords" intent of the filter UI;
      no keywords → no constraint.
    """
    pmin = query.price_min
    pmax = query.price_max
    if pmin is not None or pmax is not None:
        if raw.price_cad is None:
            return False
        if pmin is not None and raw.price_cad < pmin:
            return False
        if pmax is not None and raw.price_cad > pmax:
            return False

    bmin = query.bedrooms_min
    bmax = query.bedrooms_max
    if bmin is not None or bmax is not None:
        if raw.bedrooms is None:
            return False
        if bmin is not None and raw.bedrooms < bmin:
            return False
        if bmax is not None and raw.bedrooms > bmax:
            return False

    keywords = query.free_text_keywords or []
    if keywords:
        haystack = " ".join(
            filter(None, [raw.title, raw.address, raw.description_snippet])
        ).casefold()
        for kw in keywords:
            if kw.casefold() not in haystack:
                return False

    return True


class FixtureAdapter:
    """In-process adapter that yields pre-recorded listings for one source.

    Implements ``SourceAdapter`` so the aggregator can treat it identically
    to a live adapter. No network is touched; ``health_check`` always
    reports ``ok``. Honors the same price / bedroom / keyword filter
    contract declared in ``_PRESET_CAPABILITIES``.
    """

    method: Literal["api", "rss", "browser"] = "api"
    rate_limit_per_second: float = 1.0
    is_extractor_calibrated: bool = True
    _capabilities: ClassVar[AdapterCapabilities] = _PRESET_CAPABILITIES

    def __init__(self, name: str, listings: list[RawListing]) -> None:
        self.name = name
        self.base_url = f"https://demo.local/{name}"
        self._listings = listings
        self.capabilities: AdapterCapabilities = self._capabilities

    async def search(self, query: NormalizedQuery) -> AsyncIterator[RawListing]:
        for raw in self._listings:
            if _matches_query(raw, query):
                yield raw

    async def fetch_listing(self, listing_id: str) -> RawListing | None:
        for raw in self._listings:
            if raw.source_listing_id == listing_id:
                return raw
        return None

    async def health_check(self) -> AdapterHealth:
        return AdapterHealth(name=self.name, status="ok")

    async def close(self) -> None:
        return None


def build_demo_adapters() -> list[SourceAdapter]:
    """Return one FixtureAdapter per supported source, populated from fixtures.

    Sources that fail to load (missing fixture, parse error) are skipped
    with a warning instead of blowing up the whole API.
    """
    adapters: list[SourceAdapter] = []
    for source, loader in _LOADERS.items():
        try:
            listings = loader()
        except Exception as exc:
            log.warning("demo.loader_failed", source=source, error=str(exc))
            continue
        if not listings:
            log.warning("demo.loader_empty", source=source)
            continue
        adapters.append(FixtureAdapter(name=source, listings=listings))
        log.info("demo.adapter_built", source=source, count=len(listings))
    return adapters


# Type assertion: FixtureAdapter satisfies the Protocol.
_: SourceAdapter = FixtureAdapter(name="smoke", listings=[])
