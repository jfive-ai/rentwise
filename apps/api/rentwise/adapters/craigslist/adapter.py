"""Craigslist Vancouver RSS adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import ClassVar

import feedparser
import httpx
import structlog

from rentwise.adapters.base import (
    AdapterCapabilities,
    RobotsDisallowedError,
    SourceAdapter,
)
from rentwise.adapters.craigslist.rss_parser import parse_entry
from rentwise.adapters.craigslist.url_builder import build_search_urls
from rentwise.adapters.ratelimit import RateLimitedFetcher
from rentwise.adapters.robots import RobotsCache
from rentwise.models import AdapterHealth, NormalizedQuery, RawListing

log = structlog.get_logger(__name__)


class CraigslistAdapter:
    name = "craigslist"
    method: str = "rss"
    rate_limit_per_second: float = 1.0
    capabilities: ClassVar[AdapterCapabilities] = {
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
        self.robots = RobotsCache(user_agent=user_agent)
        self.fetcher = RateLimitedFetcher(
            rate_per_sec=self.rate_limit_per_second, jitter_ms=jitter_ms
        )

    async def _get_feed(self, url: str) -> bytes:
        if not await self.robots.is_allowed(url):
            raise RobotsDisallowedError(f"robots.txt disallows {url}")
        await self.fetcher.acquire()
        async with httpx.AsyncClient(headers={"User-Agent": self.user_agent}) as client:
            resp = await client.get(url, timeout=15)
            resp.raise_for_status()
            return resp.content

    async def search(self, query: NormalizedQuery) -> AsyncIterator[RawListing]:
        urls = build_search_urls(query, region=self.region)
        seen: set[str] = set()
        for url in urls:
            content = await self._get_feed(url)
            feed = feedparser.parse(content)
            for entry in feed.entries:
                raw = parse_entry(entry)
                if raw is None:
                    continue
                if raw.source_listing_id in seen:
                    continue
                seen.add(raw.source_listing_id)
                yield raw

    async def fetch_listing(self, listing_id: str) -> RawListing | None:
        # CL RSS doesn't expose per-listing fetches without HTML scrape (forbidden).
        return None

    async def health_check(self) -> AdapterHealth:
        url = f"{self.base_url}/search/apa?format=rss"
        try:
            if not await self.robots.is_allowed(url):
                return AdapterHealth(name=self.name, status="blocked", last_error="robots.txt")
            await self.fetcher.acquire()
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
            feed = feedparser.parse(resp.content)
            if not feed.entries:
                return AdapterHealth(name=self.name, status="degraded", last_error="no entries")
            return AdapterHealth(name=self.name, status="ok")
        except RobotsDisallowedError:
            return AdapterHealth(name=self.name, status="blocked", last_error="robots.txt")
        except httpx.HTTPError as exc:
            return AdapterHealth(name=self.name, status="degraded", last_error=str(exc))


# Type assertion: instances satisfy the Protocol
_: SourceAdapter = CraigslistAdapter(region="vancouver", user_agent="RentWise/0.1")
