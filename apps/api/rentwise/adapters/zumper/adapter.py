"""Zumper Vancouver direct adapter — scaffold.

This is a Phase-8 PR-E scaffold. It implements the SourceAdapter protocol
and is wired through the standard PlaywrightFetcher (robots check + rate
limit + identifying User-Agent), but its `_extract` is a stub that returns
an empty list with a structlog warning. We will replace `_extract` with
real selectors once we've confirmed them against rendered HTML.

TOS reality (per the issue):
    Zumper § 11 mirrors PadMapper § 8.4 (same parent — Zumper Inc.). The
    adapter is **disabled by default** behind RENTWISE_ZUMPER_ENABLED;
    do not flip it on without a current re-read of the TOS and a fresh
    robots.txt check.

URL conventions observed (best-effort, may drift):
    - Search:  https://www.zumper.com/apartments-for-rent/vancouver-bc
    - Listing: /apartment-buildings/p<ID>/<slug>
"""

from __future__ import annotations

from typing import ClassVar

import structlog

from rentwise.adapters.base import AdapterCapabilities
from rentwise.adapters.scaffold_base import ScaffoldAdapterBase
from rentwise.models import NormalizedQuery, RawListing

log = structlog.get_logger(__name__)


class ZumperAdapter(ScaffoldAdapterBase):
    name: str = "zumper"
    base_url: str = "https://www.zumper.com"
    _capabilities: ClassVar[AdapterCapabilities] = {
        # Nothing claimed yet — the search-URL builder doesn't honor any filters.
        # Add fields here as we wire them through `_search_url`.
        "supported_filters": set(),
    }

    def _search_url(self, query: NormalizedQuery) -> str:
        # Vancouver-only landing page for now. Filters will be added via
        # query-string params (e.g. ?bedrooms=2&max_rent=3000) once we
        # confirm them against the live URL contract.
        return f"{self.base_url}/apartments-for-rent/vancouver-bc"

    def _wait_for(self) -> str | None:
        # Listing cards on Zumper hang off `/apartment-buildings/p<id>/...`
        # anchors. We wait for at least one such link to render before
        # snapshotting HTML.
        return 'a[href*="/apartment-buildings/"]'

    def _extract(self, html: str, query: NormalizedQuery) -> list[RawListing]:
        # Stub: real selectors not yet confirmed. Returning [] is the safe
        # behavior — the aggregator will treat us as "no results" rather
        # than crashing on a parser error.
        log.warning(
            "zumper.extract_stub",
            note="selectors not yet confirmed against rendered HTML",
        )
        return []
