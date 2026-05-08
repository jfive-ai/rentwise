"""Nominatim client tests — uses respx to mock all HTTP."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from rentwise.enrichment.geocode import (
    GeocodeError,
    NominatimGeocoder,
)


def _hit_payload(lat: float = 49.2661, lon: float = -123.1525) -> list[dict]:
    return [
        {
            "lat": str(lat),
            "lon": str(lon),
            "display_name": "1234 W 4th Ave, Vancouver, BC",
        }
    ]


@pytest.fixture
def fast_client():
    """Return a NominatimGeocoder factory that uses ``min_interval=0`` so
    tests don't sleep for real time. Real-world throttle is exercised in
    its own test below."""

    def make(client: httpx.AsyncClient | None = None, **kwargs):
        defaults: dict = {
            "user_agent": "TestAgent/1.0",
            "min_interval_seconds": 0.0,
            "max_retries": 2,
            "timeout_seconds": 1.0,
        }
        defaults.update(kwargs)
        return NominatimGeocoder(client=client, **defaults)

    return make


@pytest.mark.asyncio
async def test_geocode_returns_result_on_hit(fast_client):
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://nominatim.openstreetmap.org") as r:
            r.get("/search").mock(return_value=httpx.Response(200, json=_hit_payload()))
            geocoder = fast_client(client=client)
            result = await geocoder.geocode("1234 W 4th Ave, Vancouver")
        assert result is not None
        assert result.lat == 49.2661
        assert result.lon == -123.1525


@pytest.mark.asyncio
async def test_geocode_returns_none_for_empty_payload(fast_client):
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://nominatim.openstreetmap.org") as r:
            r.get("/search").mock(return_value=httpx.Response(200, json=[]))
            geocoder = fast_client(client=client)
            result = await geocoder.geocode("garbage that has no match")
        assert result is None


@pytest.mark.asyncio
async def test_geocode_returns_none_for_blank_query(fast_client):
    geocoder = fast_client()
    assert await geocoder.geocode("") is None
    assert await geocoder.geocode("   ") is None


@pytest.mark.asyncio
async def test_geocode_retries_on_5xx_then_succeeds(fast_client):
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://nominatim.openstreetmap.org") as r:
            route = r.get("/search").mock(
                side_effect=[
                    httpx.Response(503, text="busy"),
                    httpx.Response(200, json=_hit_payload()),
                ]
            )
            geocoder = fast_client(client=client)
            result = await geocoder.geocode("1234 W 4th Ave, Vancouver")
        assert route.call_count == 2
        assert result is not None


@pytest.mark.asyncio
async def test_geocode_4xx_is_permanent_failure(fast_client):
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://nominatim.openstreetmap.org") as r:
            route = r.get("/search").mock(return_value=httpx.Response(400, text="bad query"))
            geocoder = fast_client(client=client)
            with pytest.raises(GeocodeError):
                await geocoder.geocode("anything")
        assert route.call_count == 1  # no retry on 400


@pytest.mark.asyncio
async def test_geocode_429_does_retry(fast_client):
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://nominatim.openstreetmap.org") as r:
            route = r.get("/search").mock(
                side_effect=[
                    httpx.Response(429, text="slow down"),
                    httpx.Response(200, json=_hit_payload()),
                ]
            )
            geocoder = fast_client(client=client)
            result = await geocoder.geocode("1234 W 4th Ave, Vancouver")
        assert route.call_count == 2
        assert result is not None


@pytest.mark.asyncio
async def test_geocode_exhausts_retries(fast_client):
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://nominatim.openstreetmap.org") as r:
            r.get("/search").mock(return_value=httpx.Response(503, text="busy"))
            geocoder = fast_client(client=client, max_retries=1)
            with pytest.raises(GeocodeError):
                await geocoder.geocode("anything")


@pytest.mark.asyncio
async def test_throttle_enforces_min_interval(fast_client):
    """Two back-to-back calls must space themselves by ≥ min_interval."""
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://nominatim.openstreetmap.org") as r:
            r.get("/search").mock(return_value=httpx.Response(200, json=_hit_payload()))
            # Use a small interval so the test doesn't take a real second.
            geocoder = fast_client(client=client, min_interval_seconds=0.05)

            loop = asyncio.get_running_loop()
            t0 = loop.time()
            await geocoder.geocode("a")
            await geocoder.geocode("b")
            elapsed = loop.time() - t0
        assert elapsed >= 0.05  # second call waited for the gate
