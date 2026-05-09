"""Shared scaffold for Playwright-based browser adapters.

Phase 8 PR-E introduces three direct adapters (Zumper, REW.ca, liv.rent)
that all share the same shape: env-var gate, robots.txt check at init,
rate-limited Playwright fetch, and a per-site `_extract` step against
rendered HTML.

The boilerplate is identical across all three; only the per-site
selectors and URL builders differ. We factor the boilerplate here so
each subclass only has to declare its `name`, `base_url`, search-page
URL builder, and an `_extract` method.

These adapters are **disabled by default** behind their own settings
flags. The HTTP wiring (`_build_adapters`) only registers them when
their flag is True, so an instance is never constructed by accident.

Per `docs/operational-rules.md`:
- robots.txt is checked at init *and* on every fetch (the Playwright
  fetcher does the per-fetch check; we add a one-shot init check so we
  can fail loudly via `health_check` rather than silently on first use).
- rate_limit_per_second is capped at 0.5 for these scaffolds — half
  the platform-wide ceiling, since these sites have stricter TOS
  language than Craigslist.
- User-Agent is the project-honest one from settings.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import ClassVar, Literal

import structlog

from rentwise.adapters.base import (
    AdapterCapabilities,
    RobotsDisallowedError,
    SourceAdapter,
)
from rentwise.adapters.playwright_fetcher import PlaywrightFetcher
from rentwise.models import AdapterHealth, NormalizedQuery, RawListing

log = structlog.get_logger(__name__)


class ScaffoldAdapterBase:
    """Base class for the Phase-8 PR-E scaffold adapters.

    Subclasses MUST set:
        - `name`: stable identifier (e.g. "zumper")
        - `base_url`: site root used for the init-time robots check
        - `_capabilities`: AdapterCapabilities ClassVar

    Subclasses MUST implement:
        - `_search_url(query)` — build the search-results URL for `query`
        - `_extract(html, query)` — parse rendered HTML into RawListing[]

    The default `_extract` returns [] with a structlog warning, which is
    the safe stub behavior when real selectors haven't been confirmed yet.
    """

    # Subclasses override these as plain class-level assignments. We
    # deliberately do NOT use ClassVar here — the SourceAdapter Protocol
    # declares these as instance variables, and mypy enforces the
    # distinction in protocol assignment.
    name: str = ""
    base_url: str = ""
    method: Literal["api", "rss", "browser"] = "browser"
    rate_limit_per_second: float = 0.5
    # Class-level signal read by the aggregator (#94). Stays False until
    # a subclass has confirmed selectors against live rendered HTML and
    # ships a non-fixture extractor test. The aggregator surfaces a
    # `degraded` source_health entry when an enabled scaffold returns
    # zero listings, so the user sees why nothing came back.
    is_extractor_calibrated: bool = False
    _capabilities: ClassVar[AdapterCapabilities] = {
        "supported_filters": set(),
    }

    def __init__(
        self,
        *,
        user_agent: str,
        jitter_ms: tuple[int, int] = (500, 1500),
        fetcher: PlaywrightFetcher | None = None,
    ) -> None:
        if not self.name or not self.base_url:
            raise NotImplementedError(
                "ScaffoldAdapterBase subclasses must set `name` and `base_url`."
            )
        self.user_agent = user_agent
        self.capabilities: AdapterCapabilities = self._capabilities
        # `fetcher` injectable for tests; default builds a real one.
        self.fetcher = fetcher or PlaywrightFetcher(
            user_agent=user_agent,
            rate_per_sec=self.rate_limit_per_second,
            jitter_ms=jitter_ms,
        )

    # ----------------- subclass extension points -----------------

    def _search_url(self, query: NormalizedQuery) -> str:
        """Build the search results URL. Default: site root."""
        return self.base_url

    def _wait_for(self) -> str | None:
        """Optional CSS selector to await before reading HTML. Override per site."""
        return None

    def _extract(self, html: str, query: NormalizedQuery) -> list[RawListing]:
        """Parse rendered HTML into RawListings. Stub returns []."""
        log.warning(
            "scaffold_adapter.extract_stub",
            adapter=self.name,
            note="real selectors not yet confirmed; returning no listings",
        )
        return []

    # ----------------- SourceAdapter Protocol -----------------

    async def search(self, query: NormalizedQuery) -> AsyncIterator[RawListing]:
        url = self._search_url(query)
        try:
            html = await self.fetcher.fetch_html(url, wait_for=self._wait_for())
        except RobotsDisallowedError:
            log.info("scaffold_adapter.robots_blocked", adapter=self.name, url=url)
            raise
        for raw in self._extract(html, query):
            yield raw

    async def fetch_listing(self, listing_id: str) -> RawListing | None:
        # Detail-page fetch isn't implemented for the scaffolds yet —
        # we only ship list-page extraction. Subclasses can override.
        return None

    async def health_check(self) -> AdapterHealth:
        """Lightweight reachability check.

        Per operational-rules § 1, robots.txt is the gate. If our path
        is Disallow'd we report `blocked` so the caller knows to skip
        this source. Calibrated subclasses (``is_extractor_calibrated =
        True``) report ``ok`` once robots is allowed; uncalibrated stubs
        report ``degraded`` so the source-health UI surfaces the reason.
        """
        url = self._search_url(NormalizedQuery())
        try:
            allowed = await self.fetcher.robots.is_allowed(url)
        except Exception as exc:
            # Robots failures are non-fatal — we report degraded but stay alive.
            log.warning("scaffold_adapter.robots_check_failed", adapter=self.name, error=str(exc))
            return AdapterHealth(name=self.name, status="degraded", last_error=str(exc))
        if not allowed:
            return AdapterHealth(name=self.name, status="blocked", last_error="robots.txt")
        if not self.is_extractor_calibrated:
            return AdapterHealth(
                name=self.name,
                status="degraded",
                last_error="scaffold: extractor not yet implemented",
            )
        return AdapterHealth(name=self.name, status="ok")

    async def close(self) -> None:
        await self.fetcher.close()


# Type assertion: a concrete subclass with `name`/`base_url` set satisfies SourceAdapter.
class _SmokeSubclass(ScaffoldAdapterBase):
    name: str = "smoke"
    base_url: str = "https://example.test"


_: SourceAdapter = _SmokeSubclass(user_agent="RentWise/0.1")
