"""Tests for the Zumper scaffold adapter.

These exercise the four required gates from the issue:
- robots.txt Disallow → blocked health, RobotsDisallowedError on search
- env-var disabled → adapter not registered in `_build_adapters`
- env-var enabled + synthetic fixture → expected output (stub: empty list)
- snippet ≤ 200 chars (vacuously true while extractor is a stub; placeholder
  guard so the constraint is asserted as soon as a real extractor lands)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from rentwise.adapters.base import RobotsDisallowedError, SourceAdapter
from rentwise.adapters.playwright_fetcher import PlaywrightFetcher
from rentwise.adapters.zumper.adapter import ZumperAdapter
from rentwise.models import NormalizedQuery

FIX = Path(__file__).resolve().parent / "fixtures"


def _make_fetcher(html: str, *, robots_allowed: bool = True) -> PlaywrightFetcher:
    fetcher = PlaywrightFetcher(user_agent="RentWise-test/0.1", jitter_ms=(0, 0))
    fetcher.robots.is_allowed = AsyncMock(return_value=robots_allowed)  # type: ignore[method-assign]
    fetcher.fetch_html = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda url, wait_for=None: (
            html
            if robots_allowed
            else (_ for _ in ()).throw(RobotsDisallowedError(f"robots blocks {url}"))
        )
    )
    return fetcher


@pytest.fixture
def fixture_html() -> str:
    return (FIX / "search_page.html").read_text()


def test_satisfies_source_adapter_protocol() -> None:
    adapter = ZumperAdapter(user_agent="RentWise-test/0.1")
    assert isinstance(adapter, SourceAdapter)
    assert adapter.name == "zumper"
    assert adapter.method == "browser"
    assert adapter.rate_limit_per_second == 0.5
    assert adapter.base_url.startswith("https://")


@pytest.mark.asyncio
async def test_search_returns_empty_for_stub_extract(fixture_html: str) -> None:
    """Stub extractor returns []; this contract is what the issue requires
    until real selectors are confirmed."""
    fetcher = _make_fetcher(fixture_html, robots_allowed=True)
    adapter = ZumperAdapter(user_agent="RentWise-test/0.1", fetcher=fetcher)
    results = [r async for r in adapter.search(NormalizedQuery())]
    assert results == []


@pytest.mark.asyncio
async def test_search_raises_on_robots_disallow() -> None:
    fetcher = _make_fetcher("", robots_allowed=False)
    adapter = ZumperAdapter(user_agent="RentWise-test/0.1", fetcher=fetcher)
    with pytest.raises(RobotsDisallowedError):
        async for _ in adapter.search(NormalizedQuery()):
            pass


@pytest.mark.asyncio
async def test_health_check_blocked_when_robots_disallows() -> None:
    fetcher = _make_fetcher("", robots_allowed=False)
    adapter = ZumperAdapter(user_agent="RentWise-test/0.1", fetcher=fetcher)
    h = await adapter.health_check()
    assert h.status == "blocked"
    assert h.last_error == "robots.txt"


@pytest.mark.asyncio
async def test_health_check_degraded_when_extractor_stubbed() -> None:
    """While the extractor is a stub, health is `degraded`, never `ok`.
    This guards against accidentally claiming a working source."""
    fetcher = _make_fetcher("<html></html>", robots_allowed=True)
    adapter = ZumperAdapter(user_agent="RentWise-test/0.1", fetcher=fetcher)
    h = await adapter.health_check()
    assert h.status == "degraded"


def test_disabled_by_default_not_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    """With RENTWISE_ZUMPER_ENABLED=false (the default), the adapter is
    NOT in the `_build_adapters` tuple. We mutate the live `settings`
    instance + clear the lru_cache rather than reloading modules — the
    latter pollutes shared state across the test session."""
    from rentwise.http import search as search_module
    from rentwise.settings import settings

    monkeypatch.setattr(settings, "rentwise_zumper_enabled", False)
    search_module._build_adapters.cache_clear()
    try:
        adapters = search_module._build_adapters()
        assert all(a.name != "zumper" for a in adapters)
    finally:
        search_module._build_adapters.cache_clear()


def test_enabled_registers_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    from rentwise.http import search as search_module
    from rentwise.settings import settings

    monkeypatch.setattr(settings, "rentwise_zumper_enabled", True)
    search_module._build_adapters.cache_clear()
    try:
        adapters = search_module._build_adapters()
        assert any(a.name == "zumper" for a in adapters)
    finally:
        search_module._build_adapters.cache_clear()


@pytest.mark.asyncio
async def test_extracted_snippets_capped_at_200_chars(fixture_html: str) -> None:
    """Once a real `_extract` lands this guards the operational rule that
    description_snippet <= 200 chars. While the stub returns [] it is
    vacuously true; the assertion still fires so the constraint is
    encoded in tests now."""
    fetcher = _make_fetcher(fixture_html, robots_allowed=True)
    adapter = ZumperAdapter(user_agent="RentWise-test/0.1", fetcher=fetcher)
    async for raw in adapter.search(NormalizedQuery()):
        if raw.description_snippet is not None:
            assert len(raw.description_snippet) <= 200
