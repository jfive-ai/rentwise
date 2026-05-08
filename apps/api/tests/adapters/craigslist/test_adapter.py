from pathlib import Path

import pytest
import respx
from httpx import Response

from rentwise.adapters.base import RobotsDisallowedError
from rentwise.adapters.craigslist.adapter import CraigslistAdapter
from rentwise.models import NormalizedQuery

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "craigslist"


@pytest.fixture
def adapter() -> CraigslistAdapter:
    return CraigslistAdapter(region="vancouver", user_agent="RentWise-test/0.1", jitter_ms=(0, 0))


@pytest.mark.asyncio
async def test_search_returns_listings(adapter):
    body = (FIX / "sample_jsonsearch.json").read_bytes()
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://vancouver.craigslist.org/robots.txt").mock(
            return_value=Response(200, text=(FIX / "robots_txt_allowed.txt").read_text())
        )
        mock.get(url__regex=r"https://vancouver\.craigslist\.org/jsonsearch/apa.*").mock(
            return_value=Response(200, content=body)
        )
        results = [r async for r in adapter.search(NormalizedQuery(bedrooms_min=2))]
    assert len(results) >= 1
    assert all(r.source == "craigslist" for r in results)
    # The JSON endpoint provides structured `bedrooms` + `price`,
    # which we now propagate verbatim instead of leaning on the title regex.
    assert any(r.bedrooms == 2.0 for r in results)
    assert any(r.price_cad is not None and r.price_cad > 0 for r in results)


@pytest.mark.asyncio
async def test_search_raises_on_robots_disallow(adapter):
    with respx.mock:
        respx.get("https://vancouver.craigslist.org/robots.txt").mock(
            return_value=Response(200, text=(FIX / "robots_txt_disallowed.txt").read_text())
        )
        with pytest.raises(RobotsDisallowedError):
            async for _ in adapter.search(NormalizedQuery()):
                pass


@pytest.mark.asyncio
async def test_capabilities_match_spec(adapter):
    caps = adapter.capabilities
    assert caps["supported_filters"] == {
        "bedrooms_min",
        "bedrooms_max",
        "price_min",
        "price_max",
        "neighborhoods",
        "free_text_keywords",
    }


@pytest.mark.asyncio
async def test_health_check_ok_on_good_payload(adapter):
    body = (FIX / "sample_jsonsearch.json").read_bytes()
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://vancouver.craigslist.org/robots.txt").mock(
            return_value=Response(200, text=(FIX / "robots_txt_allowed.txt").read_text())
        )
        mock.get(url__regex=r"https://vancouver\.craigslist\.org/jsonsearch/apa.*").mock(
            return_value=Response(200, content=body)
        )
        h = await adapter.health_check()
    assert h.status == "ok"


@pytest.mark.asyncio
async def test_health_check_degraded_on_empty_payload(adapter):
    body = (FIX / "empty_jsonsearch.json").read_bytes()
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://vancouver.craigslist.org/robots.txt").mock(
            return_value=Response(200, text=(FIX / "robots_txt_allowed.txt").read_text())
        )
        mock.get(url__regex=r"https://vancouver\.craigslist\.org/jsonsearch/apa.*").mock(
            return_value=Response(200, content=body)
        )
        h = await adapter.health_check()
    assert h.status == "degraded"


@pytest.mark.asyncio
async def test_health_check_blocked_on_403(adapter):
    """403 is what user-visible Craigslist abuse looks like in 2026 — pin
    that the adapter reports it as blocked, not 'degraded', so the
    aggregator can decide to skip the source entirely."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://vancouver.craigslist.org/robots.txt").mock(
            return_value=Response(200, text=(FIX / "robots_txt_allowed.txt").read_text())
        )
        mock.get(url__regex=r"https://vancouver\.craigslist\.org/jsonsearch/apa.*").mock(
            return_value=Response(403)
        )
        h = await adapter.health_check()
    assert h.status == "blocked"


@pytest.mark.asyncio
async def test_health_check_blocked_on_429(adapter):
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://vancouver.craigslist.org/robots.txt").mock(
            return_value=Response(200, text=(FIX / "robots_txt_allowed.txt").read_text())
        )
        mock.get(url__regex=r"https://vancouver\.craigslist\.org/jsonsearch/apa.*").mock(
            return_value=Response(429)
        )
        h = await adapter.health_check()
    assert h.status == "blocked"


@pytest.mark.asyncio
async def test_health_check_degraded_on_malformed_payload(adapter):
    """If Craigslist changes the JSON shape (wouldn't be the first time)
    we shouldn't crash — degrade gracefully so source_health surfaces it."""
    body = (FIX / "malformed_jsonsearch.json").read_bytes()
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://vancouver.craigslist.org/robots.txt").mock(
            return_value=Response(200, text=(FIX / "robots_txt_allowed.txt").read_text())
        )
        mock.get(url__regex=r"https://vancouver\.craigslist\.org/jsonsearch/apa.*").mock(
            return_value=Response(200, content=body)
        )
        h = await adapter.health_check()
    assert h.status == "degraded"
