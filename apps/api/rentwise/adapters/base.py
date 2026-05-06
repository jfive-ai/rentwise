"""Source adapter contract.

Every rental site we support is implemented as an adapter that conforms to
`SourceAdapter`. The aggregator only knows about this interface — it doesn't
care whether under the hood we're hitting an RSS feed, an HTTP API, or
driving a headless browser.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Literal, Protocol, runtime_checkable

from rentwise.models import AdapterHealth, NormalizedQuery, RawListing


@runtime_checkable
class SourceAdapter(Protocol):
    """Contract implemented by every rental source."""

    name: str
    """Stable short identifier, e.g. 'craigslist'. Used as foreign key."""

    base_url: str
    """Public homepage of the source. Used in error messages and for robots.txt."""

    method: Literal["api", "rss", "browser"]
    """How this adapter fetches data. Affects caching and rate limit policy."""

    rate_limit_per_second: float
    """Max requests per second. Always <= 1.0 for browser adapters."""

    async def search(self, query: NormalizedQuery) -> AsyncIterator[RawListing]:
        """Yield matching listings as they are found.

        Implementations MUST:
        - Honor `rate_limit_per_second` between requests.
        - Stop early on cancellation (caller may abandon the iterator).
        - Respect robots.txt for the source.
        """
        ...

    async def fetch_listing(self, listing_id: str) -> RawListing | None:
        """Fetch a single listing by source-specific ID. None if not found."""
        ...

    async def health_check(self) -> AdapterHealth:
        """Lightweight check: is this source reachable and returning data?"""
        ...
