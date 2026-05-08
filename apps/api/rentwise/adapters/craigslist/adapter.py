"""Craigslist Vancouver adapter.

Targets `/jsonsearch/apa` (JSON) instead of `/search/apa?format=rss`. The
RSS feed was deprecated by Craigslist some time before 2026-05 — direct
HEAD probes from a residential IP return HTTP 403 with three different
User-Agents, with and without the `cl_b` cookie. The JSON endpoint serves
the same listings (~4000 per request), supports the same filter params,
and is allowed by /robots.txt (only `/reply`, `/fb`, `/suggest`, `/flag`,
`/mf`, `/mailflag`, `/eaf` are disallowed).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, ClassVar, Literal

import httpx
import structlog

from rentwise.adapters.base import (
    AdapterCapabilities,
    RobotsDisallowedError,
    SourceAdapter,
)
from rentwise.adapters.craigslist.json_parser import parse_entry
from rentwise.adapters.craigslist.url_builder import build_search_urls
from rentwise.adapters.ratelimit import RateLimitedFetcher
from rentwise.adapters.robots import RobotsCache
from rentwise.models import AdapterHealth, NormalizedQuery, RawListing

log = structlog.get_logger(__name__)


def _extract_entries(payload: Any) -> list[Any]:
    """`/jsonsearch/apa` returns `[entries, metadata]` — pull entries.

    Defensive: if Craigslist changes the shape (already happened with
    the RSS feed), don't crash — return [] and let health_check report
    a degraded source.
    """
    if isinstance(payload, list) and payload and isinstance(payload[0], list):
        return payload[0]
    if isinstance(payload, list):
        return payload  # tolerate flat-list variant
    return []


class CraigslistAdapter:
    name = "craigslist"
    method: Literal["api", "rss", "browser"] = "api"
    rate_limit_per_second: float = 1.0
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
        region: str,
        user_agent: str,
        jitter_ms: tuple[int, int] = (500, 1500),
    ) -> None:
        self.region = region
        self.base_url = f"https://{region}.craigslist.org"
        self.user_agent = user_agent
        self.capabilities: AdapterCapabilities = self._capabilities
        self.robots = RobotsCache(user_agent=user_agent)
        self.fetcher = RateLimitedFetcher(
            rate_per_sec=self.rate_limit_per_second, jitter_ms=jitter_ms
        )

    async def _get_json(self, url: str) -> Any:
        if not await self.robots.is_allowed(url):
            raise RobotsDisallowedError(f"robots.txt disallows {url}")
        async with self.fetcher:
            async with httpx.AsyncClient(headers={"User-Agent": self.user_agent}) as client:
                resp = await client.get(url, timeout=15)
                resp.raise_for_status()
                return resp.json()

    async def search(self, query: NormalizedQuery) -> AsyncIterator[RawListing]:
        urls = build_search_urls(query, region=self.region)
        seen: set[str] = set()
        for url in urls:
            payload = await self._get_json(url)
            for entry in _extract_entries(payload):
                raw = parse_entry(entry)
                if raw is None:
                    continue
                if raw.source_listing_id in seen:
                    continue
                seen.add(raw.source_listing_id)
                yield raw

    async def fetch_listing(self, listing_id: str) -> RawListing | None:
        # CL doesn't expose a per-listing API endpoint we can rely on
        # without HTML scraping, which we don't do.
        return None

    async def health_check(self) -> AdapterHealth:
        url = f"{self.base_url}/jsonsearch/apa"
        try:
            if not await self.robots.is_allowed(url):
                return AdapterHealth(name=self.name, status="blocked", last_error="robots.txt")
            async with self.fetcher:
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
            try:
                payload = resp.json()
            except json.JSONDecodeError as exc:
                return AdapterHealth(
                    name=self.name, status="degraded", last_error=f"non-JSON body: {exc}"
                )
            entries = _extract_entries(payload)
            if not entries:
                return AdapterHealth(name=self.name, status="degraded", last_error="no entries")
            return AdapterHealth(name=self.name, status="ok")
        except RobotsDisallowedError:
            return AdapterHealth(name=self.name, status="blocked", last_error="robots.txt")
        except httpx.HTTPError as exc:
            return AdapterHealth(name=self.name, status="degraded", last_error=str(exc))


# Type assertion: instances satisfy the Protocol
_: SourceAdapter = CraigslistAdapter(region="vancouver", user_agent="RentWise/0.1")
