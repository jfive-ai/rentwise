"""Source adapter contract and capability projection.

Every rental site we support is implemented as an adapter that conforms to
`SourceAdapter`. The aggregator only knows about this interface — it doesn't
care whether under the hood we're hitting an RSS feed, an HTTP API, or
driving a headless browser.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Literal, Protocol, TypedDict, runtime_checkable

from rentwise.models import (
    AdapterHealth,
    FurnishedPolicy,
    NormalizedQuery,
    PetPolicy,
    RawListing,
)

SupportedFilter = Literal[
    "bedrooms_min",
    "bedrooms_max",
    "price_min",
    "price_max",
    "neighborhoods",
    "school_catchment",
    "pets",
    "furnished",
    "available_after",
    "transit_max_walk_minutes",
    "free_text_keywords",
]


class AdapterCapabilities(TypedDict):
    supported_filters: set[SupportedFilter]


_FIELD_DEFAULTS: dict[str, object] = {
    "bedrooms_min": None,
    "bedrooms_max": None,
    "price_min": None,
    "price_max": None,
    "neighborhoods": [],
    "school_catchment": None,
    "pets": PetPolicy.ANY,
    "furnished": FurnishedPolicy.ANY,
    "available_after": None,
    "transit_max_walk_minutes": None,
    "free_text_keywords": [],
}


def project_query_to_capabilities(
    query: NormalizedQuery, caps: AdapterCapabilities
) -> tuple[NormalizedQuery, list[str]]:
    """Strip query fields the adapter doesn't support; return new query + dropped names."""
    supported = caps["supported_filters"]
    data = query.model_dump()
    dropped: list[str] = []
    for field, default in _FIELD_DEFAULTS.items():
        if field in supported:
            continue
        current = data.get(field)
        if current in (None, [], PetPolicy.ANY, FurnishedPolicy.ANY):
            continue
        data[field] = default
        dropped.append(field)
    return NormalizedQuery(**data), dropped


class RobotsDisallowedError(Exception):
    """Raised when robots.txt forbids the path we want to fetch."""


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

    capabilities: AdapterCapabilities
    """Declares which NormalizedQuery fields this adapter can filter on."""

    def search(self, query: NormalizedQuery) -> AsyncIterator[RawListing]:
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
