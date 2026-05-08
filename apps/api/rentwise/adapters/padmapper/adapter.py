"""PadMapper direct adapter (scaffold, disabled by default).

Phase 8 PR-D — replaces the Phase 3 browser-extension capture path for
PadMapper. PadMapper is owned by Zumper Inc. and shares the same TOS
template (§ 8.4 prohibits scraping). Their robots.txt is more permissive
than the TOS — listing pages /rentals/... and /buildings/... are allowed
for the wildcard user-agent, but several specific paths are disallowed
and any URL containing `box=` query params is also disallowed.

The adapter:

- Honors robots.txt at fetch time via the shared RobotsCache (with an
  added defensive guard: Python's urllib.robotparser does not reliably
  parse `Disallow: /*box=*` wildcard query-param patterns, so we also
  enforce it explicitly here, plus the documented path Disallows).
- Identifies honestly via settings.user_agent ("RentWise/...").
- Caps rate at 0.5 req/sec per source, with the standard jitter window.
- Is disabled by default and only registered when
  RENTWISE_PADMAPPER_ENABLED=true (see settings.py + http/search.py).

Selector strategy: the search results page is rendered client-side, so a
single static HTML inspection is not sufficient. _extract is a stub that
returns []; tests use synthetic HTML fixtures only. Live scraping will
land in a follow-up PR once the rendered DOM is mapped.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import ClassVar, Literal
from urllib.parse import parse_qs, quote, urlparse

import structlog

from rentwise.adapters.base import (
    AdapterCapabilities,
    RobotsDisallowedError,
    SourceAdapter,
)
from rentwise.adapters.playwright_fetcher import PlaywrightFetcher
from rentwise.models import AdapterHealth, NormalizedQuery, RawListing

log = structlog.get_logger(__name__)

# Paths explicitly disallowed by https://padmapper.com/robots.txt for the
# wildcard user-agent. We mirror these here as a defensive guard because
# Python's urllib.robotparser handles wildcard query params unreliably,
# and because we want a clear in-process tripwire if a future bug ever
# causes us to construct a disallowed URL.
_DISALLOWED_PREFIXES: tuple[str, ...] = (
    "/api",
    "/backlinks",
    "/external",
    "/static",
)

# Path patterns where any /<segment>/<id>/cost-calculator is disallowed.
_DISALLOWED_COST_CALCULATOR_ROOTS: tuple[str, ...] = ("/buildings/", "/rentals/")


def _path_is_disallowed(path: str) -> bool:
    """Return True if `path` matches a robots.txt-disallowed prefix."""
    for prefix in _DISALLOWED_PREFIXES:
        # Matches /api, /api/, /api/foo — but NOT /apartments.
        if path == prefix or path.startswith(prefix + "/"):
            return True
    for root in _DISALLOWED_COST_CALCULATOR_ROOTS:
        if path.startswith(root) and path.endswith("/cost-calculator"):
            return True
    return False


def _query_has_box_param(query: str) -> bool:
    """Return True if the URL's query string includes any `box=` param.

    PadMapper's robots.txt disallows any URL with a `box=` query parameter
    (used for map viewport bounds). We enforce this explicitly because
    Python's urllib.robotparser doesn't parse `Disallow: /*box=*` wildcards.
    """
    return "box" in parse_qs(query, keep_blank_values=True)


def is_url_allowed(url: str) -> bool:
    """Return True if `url` is allowed under PadMapper's robots.txt rules.

    Combines the path-prefix Disallows and the `box=` query-param Disallow
    into one helper so callers get a single source of truth.
    """
    parsed = urlparse(url)
    if _path_is_disallowed(parsed.path):
        return False
    if _query_has_box_param(parsed.query):
        return False
    return True


class PadMapperAdapter:
    """Direct adapter for padmapper.com.

    Disabled by default. Register from http/search.py only when
    `settings.rentwise_padmapper_enabled` is True.
    """

    name = "padmapper"
    method: Literal["api", "rss", "browser"] = "browser"
    rate_limit_per_second: float = 0.5
    _capabilities: ClassVar[AdapterCapabilities] = {
        "supported_filters": {
            "bedrooms_min",
            "bedrooms_max",
            "price_min",
            "price_max",
            "neighborhoods",
            "free_text_keywords",
        }
    }

    def __init__(
        self,
        *,
        user_agent: str,
        jitter_ms: tuple[int, int] = (500, 1500),
        fetcher: PlaywrightFetcher | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.base_url = "https://padmapper.com"
        self.capabilities: AdapterCapabilities = self._capabilities
        self.fetcher = fetcher or PlaywrightFetcher(
            user_agent=user_agent,
            rate_per_sec=self.rate_limit_per_second,
            jitter_ms=jitter_ms,
        )

    def _build_search_url(self, query: NormalizedQuery) -> str:
        """Build a search URL that never includes a `box=` parameter.

        We use the city-scoped search page (/apartments/vancouver-bc) and
        layer simple filters via path/query segments. Map-viewport filters
        (which would use `box=`) are NOT supported.
        """
        url = f"{self.base_url}/apartments/vancouver-bc"
        params: list[str] = []
        if query.price_min is not None:
            params.append(f"min-price={int(query.price_min)}")
        if query.price_max is not None:
            params.append(f"max-price={int(query.price_max)}")
        if query.bedrooms_min is not None:
            params.append(f"min-beds={query.bedrooms_min}")
        if query.bedrooms_max is not None:
            params.append(f"max-beds={query.bedrooms_max}")
        if query.free_text_keywords:
            kw = " ".join(query.free_text_keywords)
            params.append(f"keyword={quote(kw)}")
        if params:
            url = f"{url}?{'&'.join(params)}"
        return url

    async def _fetch(self, url: str) -> str:
        """Fetch a URL after the robots.txt + explicit-disallow guards."""
        if not is_url_allowed(url):
            raise RobotsDisallowedError(f"PadMapper disallows {url}")
        return await self.fetcher.fetch_html(url)

    def _extract(self, html: str) -> list[RawListing]:
        """Parse rendered listing cards from search-results HTML.

        Stub: PadMapper renders results client-side, so a static HTML
        inspection isn't enough to produce stable selectors. Returning an
        empty list keeps the adapter safely inert until the selectors are
        mapped in a follow-up PR. Tests assert the stub returns [] for
        the synthetic fixture.
        """
        _ = html
        return []

    async def search(self, query: NormalizedQuery) -> AsyncIterator[RawListing]:
        url = self._build_search_url(query)
        html = await self._fetch(url)
        for raw in self._extract(html):
            yield raw

    async def fetch_listing(self, listing_id: str) -> RawListing | None:
        # Per-listing fetch is unimplemented in the scaffold. Disallowed
        # paths (cost-calculator, /api/...) would be caught by is_url_allowed
        # if a future implementation accidentally builds one of them.
        _ = listing_id
        return None

    async def health_check(self) -> AdapterHealth:
        url = f"{self.base_url}/apartments/vancouver-bc"
        try:
            if not is_url_allowed(url):
                return AdapterHealth(name=self.name, status="blocked", last_error="robots.txt")
            if not await self.fetcher.robots.is_allowed(url):
                return AdapterHealth(name=self.name, status="blocked", last_error="robots.txt")
            return AdapterHealth(name=self.name, status="ok")
        except RobotsDisallowedError:
            return AdapterHealth(name=self.name, status="blocked", last_error="robots.txt")

    async def close(self) -> None:
        await self.fetcher.close()


# Type assertion: instances satisfy the Protocol.
_: SourceAdapter = PadMapperAdapter(user_agent="RentWise/0.1")
