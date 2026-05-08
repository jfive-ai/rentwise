"""REW.ca Vancouver direct adapter — scaffold.

This is a Phase-8 PR-E scaffold. It implements the SourceAdapter protocol
and is wired through the standard PlaywrightFetcher (robots check + rate
limit + identifying User-Agent), but its `_extract` is a stub that returns
an empty list with a structlog warning. We will replace `_extract` with
real selectors once we've confirmed them against rendered HTML.

TOS reality (per the issue):
    REW.ca's TOS forbids "robot, spider, or other automatic device,
    process, or means" *and* names "screen scraping" / "database
    scraping" explicitly. This is the most explicit anti-scraping
    language of the three sources in this PR. The adapter is **disabled
    by default** behind RENTWISE_REW_ENABLED; do not flip it on without
    a current re-read of the TOS, a fresh robots.txt check, and a
    deliberate decision about whether the personal-use single-user
    rationale still holds.

URL conventions observed (best-effort, may drift):
    - Search:  https://www.rew.ca/properties/areas/vancouver-bc
    - Listing: /properties/<address-slug>-vancouver-bc
"""

from __future__ import annotations

from typing import ClassVar

import structlog

from rentwise.adapters.base import AdapterCapabilities
from rentwise.adapters.scaffold_base import ScaffoldAdapterBase
from rentwise.models import NormalizedQuery, RawListing

log = structlog.get_logger(__name__)


class RewAdapter(ScaffoldAdapterBase):
    name: str = "rew"
    base_url: str = "https://www.rew.ca"
    _capabilities: ClassVar[AdapterCapabilities] = {
        "supported_filters": set(),
    }

    def _search_url(self, query: NormalizedQuery) -> str:
        return f"{self.base_url}/properties/areas/vancouver-bc"

    def _wait_for(self) -> str | None:
        # REW.ca property cards link to `/properties/<slug>-<region>`.
        return 'a[href*="/properties/"]'

    def _extract(self, html: str, query: NormalizedQuery) -> list[RawListing]:
        log.warning(
            "rew.extract_stub",
            note="selectors not yet confirmed against rendered HTML",
        )
        return []
