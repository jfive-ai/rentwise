"""Per-origin robots.txt fetcher and parser."""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import structlog

log = structlog.get_logger(__name__)


class RobotsCache:
    def __init__(self, user_agent: str) -> None:
        self.user_agent = user_agent
        self._parsers: dict[str, RobotFileParser] = {}
        self._lock = asyncio.Lock()

    async def is_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        async with self._lock:
            parser = self._parsers.get(origin)
            if parser is None:
                parser = await self._fetch_parser(origin)
                self._parsers[origin] = parser

        return parser.can_fetch(self.user_agent, url)

    async def _fetch_parser(self, origin: str) -> RobotFileParser:
        parser = RobotFileParser()
        url = f"{origin}/robots.txt"
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(url, headers={"User-Agent": self.user_agent})
            if resp.status_code == 200:
                parser.parse(resp.text.splitlines())
            else:
                # Per RFC 9309, 4xx → allow all
                parser.parse(["User-agent: *", "Allow: /"])
        except httpx.HTTPError as exc:
            log.warning("robots.fetch_failed", origin=origin, error=str(exc))
            parser.parse(["User-agent: *", "Allow: /"])
        return parser
