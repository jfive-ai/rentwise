"""Async Nominatim client.

Free tier; the relevant ToS rules:
- ≤ 1 req/sec global. We enforce with an asyncio.Lock + monotonic-time gate.
- Honest, contactable User-Agent. We pass `settings.user_agent`.
- Cache locally. The DB-level cache lives in storage; this module is the
  network boundary.

Network errors propagate as :class:`GeocodeError` so the caller (the
:class:`EnrichmentService`) can decide whether to record a negative
cache row or skip silently. Timeouts and 5xx use exponential backoff.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Protocol

import httpx
import structlog

log = structlog.get_logger(__name__)


class GeocodeError(Exception):
    """Network or upstream error during a geocode lookup."""


@dataclass(frozen=True)
class GeocodeResult:
    lat: float
    lon: float
    display_name: str | None = None


class Geocoder(Protocol):
    """Minimal protocol so tests can swap in a fake."""

    async def geocode(self, query: str) -> GeocodeResult | None:
        """Return the best match for ``query``, or ``None`` for no result."""
        ...


class NominatimGeocoder:
    """Production Nominatim client.

    Concurrency: a single asyncio.Lock serializes outgoing requests, and a
    monotonic-time gate enforces the 1 req/sec floor so two callers in the
    same process can't accidentally double-up. This is **not** safe across
    processes — if you ever run multiple workers, deploy a shared rate
    limiter (Redis, etc.) before then.
    """

    def __init__(
        self,
        *,
        base_url: str = "https://nominatim.openstreetmap.org",
        user_agent: str,
        timeout_seconds: float = 5.0,
        min_interval_seconds: float = 1.0,
        max_retries: int = 2,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent
        self._timeout = timeout_seconds
        self._min_interval = min_interval_seconds
        self._max_retries = max_retries
        self._lock = asyncio.Lock()
        self._next_allowed_at = 0.0
        # Allow a caller-supplied client (lets tests patch it via respx) but
        # default to a fresh one. The caller is responsible for closing
        # whatever they pass in.
        self._client = client
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def geocode(self, query: str) -> GeocodeResult | None:
        if not query.strip():
            return None
        params = {
            "q": query,
            "format": "json",
            "limit": "1",
            "addressdetails": "0",
            "countrycodes": "ca",
        }
        for attempt in range(self._max_retries + 1):
            try:
                payload = await self._request(params)
            except httpx.TimeoutException as exc:
                log.warning("nominatim.timeout", query=query, attempt=attempt, error=str(exc))
                if attempt >= self._max_retries:
                    raise GeocodeError("timeout") from exc
                await asyncio.sleep(self._backoff_delay(attempt))
                continue
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                # 4xx (other than 429) is permanent; don't retry.
                if 400 <= status < 500 and status != 429:
                    log.warning("nominatim.client_error", query=query, status=status)
                    raise GeocodeError(f"http_{status}") from exc
                log.warning(
                    "nominatim.transient_error", query=query, status=status, attempt=attempt
                )
                if attempt >= self._max_retries:
                    raise GeocodeError(f"http_{status}") from exc
                await asyncio.sleep(self._backoff_delay(attempt))
                continue
            except httpx.HTTPError as exc:
                log.warning("nominatim.network_error", query=query, error=str(exc))
                if attempt >= self._max_retries:
                    raise GeocodeError("network") from exc
                await asyncio.sleep(self._backoff_delay(attempt))
                continue

            return self._parse(payload)
        raise GeocodeError("exhausted_retries")

    async def _request(self, params: dict[str, str]) -> list[dict[str, object]]:
        # Throttle: only one outstanding request, and ≥ min_interval between
        # request *starts*. If a previous request hasn't expired its slot yet,
        # sleep for the remainder.
        async with self._lock:
            now = time.monotonic()
            if now < self._next_allowed_at:
                await asyncio.sleep(self._next_allowed_at - now)
            self._next_allowed_at = time.monotonic() + self._min_interval

            client = self._client or httpx.AsyncClient(timeout=self._timeout)
            try:
                resp = await client.get(
                    f"{self._base_url}/search",
                    params=params,
                    headers={"User-Agent": self._user_agent, "Accept-Language": "en"},
                )
                resp.raise_for_status()
                payload = resp.json()
                if not isinstance(payload, list):
                    return []
                return payload
            finally:
                if self._client is None:
                    await client.aclose()

    @staticmethod
    def _parse(payload: list[dict[str, object]]) -> GeocodeResult | None:
        if not payload:
            return None
        first = payload[0]
        raw_lat = first.get("lat")
        raw_lon = first.get("lon")
        try:
            lat = float(str(raw_lat))
            lon = float(str(raw_lon))
        except (TypeError, ValueError):
            return None
        display = first.get("display_name")
        return GeocodeResult(
            lat=lat,
            lon=lon,
            display_name=str(display) if isinstance(display, str) else None,
        )

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        # 0.5s, 1.0s, 2.0s … capped at 4s.
        delay: float = min(0.5 * (2**attempt), 4.0)
        return delay
