import pytest
import respx
from httpx import Response

from rentwise.adapters.robots import RobotsCache


@pytest.fixture
def allowing_txt():
    return "User-agent: *\nAllow: /\n"


@pytest.fixture
def disallowing_txt():
    return "User-agent: *\nDisallow: /search\n"


@pytest.mark.asyncio
async def test_allows_when_robots_allows(allowing_txt):
    cache = RobotsCache(user_agent="RentWise/0.1")
    with respx.mock:
        respx.get("https://example.com/robots.txt").mock(
            return_value=Response(200, text=allowing_txt)
        )
        assert await cache.is_allowed("https://example.com/search/x") is True


@pytest.mark.asyncio
async def test_disallows_when_robots_blocks(disallowing_txt):
    cache = RobotsCache(user_agent="RentWise/0.1")
    with respx.mock:
        respx.get("https://example.com/robots.txt").mock(
            return_value=Response(200, text=disallowing_txt)
        )
        assert await cache.is_allowed("https://example.com/search/x") is False


@pytest.mark.asyncio
async def test_caches_per_origin(allowing_txt):
    cache = RobotsCache(user_agent="RentWise/0.1")
    with respx.mock:
        route = respx.get("https://example.com/robots.txt").mock(
            return_value=Response(200, text=allowing_txt)
        )
        await cache.is_allowed("https://example.com/a")
        await cache.is_allowed("https://example.com/b")
        assert route.call_count == 1


@pytest.mark.asyncio
async def test_404_treated_as_allow():
    cache = RobotsCache(user_agent="RentWise/0.1")
    with respx.mock:
        respx.get("https://example.com/robots.txt").mock(return_value=Response(404))
        assert await cache.is_allowed("https://example.com/anything") is True
