"""liv.rent Vancouver direct adapter — scaffold.

This is a Phase-8 PR-E scaffold. It implements the SourceAdapter protocol
and is wired through the standard PlaywrightFetcher (robots check + rate
limit + identifying User-Agent), but its `_extract` is a stub that returns
an empty list with a structlog warning. We will replace `_extract` with
real selectors once we've confirmed them against rendered HTML.

TOS reality (per the issue):
    liv.rent § 7.1(v)/(w) prohibits scraping/indexing/data-mining and
    bot use. liv.rent is a Vancouver-based startup; an explicit
    partnership is likely a more durable long-term path than an
    adversarial adapter. That work is non-engineering and out of scope
    here. The adapter is **disabled by default** behind
    RENTWISE_LIVRENT_ENABLED.

URL conventions observed (best-effort, may drift):
    - Search:  https://liv.rent/rental-listings/city/vancouver
"""

from __future__ import annotations

from typing import ClassVar

import structlog

from rentwise.adapters.base import AdapterCapabilities
from rentwise.adapters.scaffold_base import ScaffoldAdapterBase
from rentwise.models import NormalizedQuery, RawListing

log = structlog.get_logger(__name__)


class LivRentAdapter(ScaffoldAdapterBase):
    name: str = "livrent"
    base_url: str = "https://liv.rent"
    _capabilities: ClassVar[AdapterCapabilities] = {
        "supported_filters": set(),
    }

    def _search_url(self, query: NormalizedQuery) -> str:
        return f"{self.base_url}/rental-listings/city/vancouver"

    def _wait_for(self) -> str | None:
        # liv.rent renders listing cards client-side. Wait for any anchor
        # under the rental-listings tree before snapshotting.
        return 'a[href*="/rental-listings/"]'

    def _extract(self, html: str, query: NormalizedQuery) -> list[RawListing]:
        log.warning(
            "livrent.extract_stub",
            note="selectors not yet confirmed against rendered HTML",
        )
        return []
