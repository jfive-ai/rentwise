# Phase 3: Playwright Adapter Base + Rentals.ca Adapter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a reusable Playwright fetcher (browser + ratelimit + robots) and the first browser-based source adapter (Rentals.ca), so `/search` aggregates both Craigslist (RSS) and Rentals.ca (browser).

**Architecture:** Composition over inheritance, mirroring how `CraigslistAdapter` composes `RateLimitedFetcher` + `RobotsCache`. A new `PlaywrightFetcher` wraps a single shared Chromium browser and exposes `fetch_html(url, *, wait_for=None) -> str`, integrating robots + ratelimit per call. `RentalsCaAdapter` composes a `PlaywrightFetcher` and uses pure-function URL builders + HTML parsers (testable in isolation against recorded HTML fixtures). The Rentals.ca implementation is **gated on a TOS verification task** that must complete before adapter work begins.

**Tech Stack:** `playwright` (already in `pyproject.toml`), `selectolax` for fast HTML parsing (new dep), existing `RateLimitedFetcher`, `RobotsCache`, `SourceAdapter` Protocol.

---

## Spec references

- Issue: https://github.com/jfive-ai/rentwise/issues/13
- Constraints: `docs/legal.md` (TOS check required, ≤1 req/sec, snippets ≤200 chars, no re-hosted photos), `CLAUDE.md` § "Working on adapters"
- Roadmap: `docs/roadmap.md` Phase 3
- Existing patterns to mirror: `apps/api/rentwise/adapters/craigslist/`

## File structure

**Create:**
- `apps/api/rentwise/adapters/playwright_fetcher.py` — `PlaywrightFetcher` class
- `apps/api/rentwise/adapters/rentals_ca/__init__.py`
- `apps/api/rentwise/adapters/rentals_ca/adapter.py` — `RentalsCaAdapter`
- `apps/api/rentwise/adapters/rentals_ca/url_builder.py` — pure: `build_search_url(query) -> str`
- `apps/api/rentwise/adapters/rentals_ca/html_parser.py` — pure: `parse_listing_cards(html) -> list[RawListing]`
- `apps/api/tests/adapters/test_playwright_fetcher.py`
- `apps/api/tests/adapters/rentals_ca/__init__.py`
- `apps/api/tests/adapters/rentals_ca/test_adapter.py`
- `apps/api/tests/adapters/rentals_ca/test_url_builder.py`
- `apps/api/tests/adapters/rentals_ca/test_html_parser.py`
- `apps/api/tests/fixtures/rentals_ca/sample_listings.html` — recorded HTML
- `apps/api/tests/fixtures/rentals_ca/empty.html`
- `apps/api/scripts/record_rentals_ca_fixture.py` — one-off recorder

**Modify:**
- `apps/api/pyproject.toml` — add `selectolax>=0.3.21` dep
- `apps/api/rentwise/http/search.py:17-27` — register `RentalsCaAdapter` in `_build_adapters()`
- `apps/api/rentwise/settings.py` — add `rentals_ca_region: str = "vancouver"`
- `docs/legal.md` — add Rentals.ca TOS findings + per-source notes
- `docs/roadmap.md` — tick Phase 3 items as completed
- `README.md` — add Rentals.ca to source list

---

## Task 0 — Verify Rentals.ca TOS

**This task gates Tasks 2-5.** If TOS prohibits automated access, stop after Task 1, file a follow-up issue documenting the finding, and skip the adapter implementation.

**Files:**
- Modify: `docs/legal.md`

- [ ] **Step 1: Load Rentals.ca TOS in a real browser**

The page returns 403 to non-browser clients (verified). Use one of:
- A real desktop browser to navigate to `https://rentals.ca/terms-of-use` (and `/terms`, `/legal`, footer links from `https://rentals.ca`)
- A throwaway Playwright script with the project user agent: `playwright codegen rentals.ca`

- [ ] **Step 2: Search the TOS for restrictive clauses**

Look for these terms (case-insensitive): `automated`, `automatic`, `scrap`, `crawl`, `bot`, `robot`, `data mining`, `programmatic`, `extract`, `harvest`, `spider`, `agent`, `intellectual property`. Quote any matching clauses verbatim — do not paraphrase.

- [ ] **Step 3: Document findings in `docs/legal.md`**

Add a new sub-section under "### liv.rent, PadMapper, Zumper, Rentals.ca, REW.ca" with this structure:

```markdown
### Rentals.ca (verified YYYY-MM-DD)

**robots.txt:** Allow `/`, disallow only `*-feed.json`, `*-feed.xml`, and pages with `bbox=`, `amenities=`, `types=` query params. Crawl-delay: not specified.

**Terms of Use (URL):** [paste URL here]

**Relevant clauses (verbatim):**
> [quoted clause 1]
> [quoted clause 2]

**Decision:** [ALLOWED | PROHIBITED | UNCLEAR]

**If PROHIBITED:** stop adapter work; file follow-up issue. Optional pivot: user-driven mode (browser extension watches user-visited pages).
**If ALLOWED:** proceed; metadata only, snippets ≤200 chars, no re-hosted photos, ≤1 req/sec.
```

- [ ] **Step 4: Commit**

```bash
git add docs/legal.md
git commit -m "docs(legal): verify Rentals.ca TOS for Phase 3 adapter (#13)"
```

- [ ] **Step 5: Branch decision**

If decision = PROHIBITED → stop, comment on issue #13 with the finding, file follow-up #14 to investigate user-driven mode for Rentals.ca, **but still execute Task 1** (Playwright base class is independent and unblocks PadMapper/Zumper/REW/liv.rent).

If decision = ALLOWED → proceed through all tasks.

If decision = UNCLEAR → ask the human owner before proceeding to Tasks 2-5.

---

## Task 1 — `PlaywrightFetcher` class

A composable fetcher that owns one Chromium browser per instance, integrates `RobotsCache` + `RateLimitedFetcher`, and exposes `fetch_html`.

**Files:**
- Create: `apps/api/rentwise/adapters/playwright_fetcher.py`
- Create: `apps/api/tests/adapters/test_playwright_fetcher.py`

- [ ] **Step 1: Write the failing tests**

```python
# apps/api/tests/adapters/test_playwright_fetcher.py
"""Tests for PlaywrightFetcher.

We mock the Playwright objects entirely — these tests verify wiring
(robots check, rate-limit, browser lifecycle), not real browser behavior.
A separate slow integration test (out of scope here) would cover real Chromium.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rentwise.adapters.base import RobotsDisallowedError
from rentwise.adapters.playwright_fetcher import PlaywrightFetcher


@pytest.fixture
def fake_page() -> MagicMock:
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.content = AsyncMock(return_value="<html>ok</html>")
    page.close = AsyncMock()
    return page


@pytest.fixture
def fake_context(fake_page: MagicMock) -> MagicMock:
    ctx = MagicMock()
    ctx.new_page = AsyncMock(return_value=fake_page)
    ctx.close = AsyncMock()
    return ctx


@pytest.fixture
def fake_browser(fake_context: MagicMock) -> MagicMock:
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=fake_context)
    browser.close = AsyncMock()
    return browser


@pytest.fixture
def fake_pw(fake_browser: MagicMock) -> MagicMock:
    pw = MagicMock()
    pw.chromium.launch = AsyncMock(return_value=fake_browser)
    pw.stop = AsyncMock()
    return pw


async def test_lazy_browser_start(fake_pw: MagicMock, fake_page: MagicMock) -> None:
    """The browser is not launched until the first fetch."""
    with patch(
        "rentwise.adapters.playwright_fetcher.async_playwright"
    ) as start_pw:
        start_pw.return_value.start = AsyncMock(return_value=fake_pw)

        fetcher = PlaywrightFetcher(user_agent="RentWise/test")
        # Override robots to always allow
        fetcher.robots.is_allowed = AsyncMock(return_value=True)

        # Browser not yet launched
        fake_pw.chromium.launch.assert_not_called()

        html = await fetcher.fetch_html("https://example.test/page")
        assert html == "<html>ok</html>"
        fake_pw.chromium.launch.assert_awaited_once()

        # Second call reuses the same browser
        await fetcher.fetch_html("https://example.test/other")
        fake_pw.chromium.launch.assert_awaited_once()

        await fetcher.close()
        fake_pw.stop.assert_awaited_once()


async def test_robots_disallowed_raises(fake_pw: MagicMock) -> None:
    """RobotsDisallowedError when robots forbids the URL — browser never opens."""
    with patch(
        "rentwise.adapters.playwright_fetcher.async_playwright"
    ) as start_pw:
        start_pw.return_value.start = AsyncMock(return_value=fake_pw)

        fetcher = PlaywrightFetcher(user_agent="RentWise/test")
        fetcher.robots.is_allowed = AsyncMock(return_value=False)

        with pytest.raises(RobotsDisallowedError):
            await fetcher.fetch_html("https://blocked.test/page")

        fake_pw.chromium.launch.assert_not_called()


async def test_passes_wait_for_selector(
    fake_pw: MagicMock, fake_page: MagicMock
) -> None:
    """wait_for kwarg is forwarded to page.wait_for_selector."""
    with patch(
        "rentwise.adapters.playwright_fetcher.async_playwright"
    ) as start_pw:
        start_pw.return_value.start = AsyncMock(return_value=fake_pw)

        fetcher = PlaywrightFetcher(user_agent="RentWise/test")
        fetcher.robots.is_allowed = AsyncMock(return_value=True)

        await fetcher.fetch_html("https://example.test/", wait_for=".listing-card")
        fake_page.wait_for_selector.assert_awaited_once_with(
            ".listing-card", timeout=10000
        )


async def test_close_is_idempotent(fake_pw: MagicMock) -> None:
    """close() before any fetch is a no-op; close() twice is safe."""
    with patch(
        "rentwise.adapters.playwright_fetcher.async_playwright"
    ) as start_pw:
        start_pw.return_value.start = AsyncMock(return_value=fake_pw)

        fetcher = PlaywrightFetcher(user_agent="RentWise/test")

        await fetcher.close()  # never started — no-op
        await fetcher.close()  # double-close — no-op
        fake_pw.stop.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd apps/api
uv run pytest tests/adapters/test_playwright_fetcher.py -v
```

Expected: ImportError — `PlaywrightFetcher` does not exist.

- [ ] **Step 3: Write the implementation**

```python
# apps/api/rentwise/adapters/playwright_fetcher.py
"""Browser fetcher: composes RobotsCache + RateLimitedFetcher + Chromium.

One instance per adapter — keeps a single browser process alive for the
adapter's lifetime, opens a fresh page per request, closes it after.
Subclasses of SourceAdapter compose this and call `fetch_html`.
"""

from __future__ import annotations

import structlog
from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from rentwise.adapters.base import RobotsDisallowedError
from rentwise.adapters.ratelimit import RateLimitedFetcher
from rentwise.adapters.robots import RobotsCache

log = structlog.get_logger(__name__)


class PlaywrightFetcher:
    """Composable browser fetcher with robots + rate-limit integration."""

    def __init__(
        self,
        *,
        user_agent: str,
        rate_per_sec: float = 1.0,
        jitter_ms: tuple[int, int] = (500, 1500),
        page_timeout_ms: int = 30_000,
        selector_timeout_ms: int = 10_000,
    ) -> None:
        self.user_agent = user_agent
        self.page_timeout_ms = page_timeout_ms
        self.selector_timeout_ms = selector_timeout_ms
        self.robots = RobotsCache(user_agent=user_agent)
        self.fetcher = RateLimitedFetcher(rate_per_sec=rate_per_sec, jitter_ms=jitter_ms)
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def _ensure_browser(self) -> BrowserContext:
        if self._context is not None:
            return self._context
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)
        self._context = await self._browser.new_context(user_agent=self.user_agent)
        log.info("playwright.browser.started", user_agent=self.user_agent)
        return self._context

    async def fetch_html(self, url: str, *, wait_for: str | None = None) -> str:
        """Fetch rendered HTML, respecting robots + rate limits.

        Raises RobotsDisallowedError if robots.txt forbids the URL.
        """
        if not await self.robots.is_allowed(url):
            raise RobotsDisallowedError(f"robots.txt disallows {url}")
        async with self.fetcher:
            ctx = await self._ensure_browser()
            page = await ctx.new_page()
            try:
                await page.goto(
                    url, wait_until="domcontentloaded", timeout=self.page_timeout_ms
                )
                if wait_for:
                    await page.wait_for_selector(
                        wait_for, timeout=self.selector_timeout_ms
                    )
                return await page.content()
            finally:
                await page.close()

    async def close(self) -> None:
        """Idempotent shutdown."""
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._pw is not None:
            await self._pw.stop()
            self._pw = None
        self._context = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/adapters/test_playwright_fetcher.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check rentwise/adapters/playwright_fetcher.py tests/adapters/test_playwright_fetcher.py
uv run ruff format --check rentwise/adapters/playwright_fetcher.py
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add rentwise/adapters/playwright_fetcher.py tests/adapters/test_playwright_fetcher.py
git commit -m "feat(api): add PlaywrightFetcher with robots + rate-limit integration (#13)"
```

---

## Task 2 — Rentals.ca URL builder

Pure function: `NormalizedQuery → search URL`. Mirrors `craigslist/url_builder.py`.

**Files:**
- Create: `apps/api/rentwise/adapters/rentals_ca/__init__.py` (single line: `"""Rentals.ca adapter."""`)
- Create: `apps/api/rentwise/adapters/rentals_ca/url_builder.py`
- Create: `apps/api/tests/adapters/rentals_ca/__init__.py` (empty)
- Create: `apps/api/tests/adapters/rentals_ca/test_url_builder.py`

**Prerequisite:** Task 0 returned ALLOWED. Skip if PROHIBITED.

- [ ] **Step 1: Confirm the search URL pattern**

Open `https://rentals.ca/vancouver` in a browser. Apply filters: 2 bedrooms, max $3000. Note the resulting URL pattern. As of writing, Rentals.ca uses path segments + query params, e.g.:

```
https://rentals.ca/vancouver?p_min=0&p_max=3000&beds_min=2
```

If the pattern differs, update the implementation below to match. Document the observed pattern as a top-of-file docstring in `url_builder.py`.

- [ ] **Step 2: Write the failing tests**

```python
# apps/api/tests/adapters/rentals_ca/test_url_builder.py
from rentwise.adapters.rentals_ca.url_builder import build_search_url
from rentwise.models import NormalizedQuery


def test_minimum_query() -> None:
    url = build_search_url(NormalizedQuery(), region="vancouver")
    assert url == "https://rentals.ca/vancouver"


def test_with_bedrooms_min() -> None:
    url = build_search_url(NormalizedQuery(bedrooms_min=2), region="vancouver")
    assert "beds_min=2" in url
    assert url.startswith("https://rentals.ca/vancouver?")


def test_with_price_range() -> None:
    url = build_search_url(
        NormalizedQuery(price_min=1500, price_max=3000), region="vancouver"
    )
    assert "p_min=1500" in url
    assert "p_max=3000" in url


def test_alternate_region() -> None:
    url = build_search_url(NormalizedQuery(), region="toronto")
    assert url.startswith("https://rentals.ca/toronto")
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/adapters/rentals_ca/test_url_builder.py -v
```

Expected: ImportError.

- [ ] **Step 4: Write the implementation**

```python
# apps/api/rentwise/adapters/rentals_ca/url_builder.py
"""Build Rentals.ca search URLs from a NormalizedQuery.

URL pattern observed YYYY-MM-DD: https://rentals.ca/<region>?p_min=&p_max=&beds_min=
Update this docstring (and the params dict) if the site changes its query format.
"""

from __future__ import annotations

from urllib.parse import urlencode

from rentwise.models import NormalizedQuery


def build_search_url(query: NormalizedQuery, *, region: str) -> str:
    base = f"https://rentals.ca/{region}"
    params: dict[str, int] = {}
    if query.price_min is not None:
        params["p_min"] = query.price_min
    if query.price_max is not None:
        params["p_max"] = query.price_max
    if query.bedrooms_min is not None:
        params["beds_min"] = query.bedrooms_min
    if not params:
        return base
    return f"{base}?{urlencode(params)}"
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/adapters/rentals_ca/test_url_builder.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add rentwise/adapters/rentals_ca/__init__.py rentwise/adapters/rentals_ca/url_builder.py tests/adapters/rentals_ca/
git commit -m "feat(api): rentals.ca url_builder for search filters (#13)"
```

---

## Task 3 — Rentals.ca HTML parser

Pure function: `html → list[RawListing]`. Tested against a recorded fixture so we never hit live rentals.ca in CI.

**Files:**
- Create: `apps/api/rentwise/adapters/rentals_ca/html_parser.py`
- Create: `apps/api/scripts/record_rentals_ca_fixture.py`
- Create: `apps/api/tests/fixtures/rentals_ca/sample_listings.html` (recorded — see Step 1)
- Create: `apps/api/tests/fixtures/rentals_ca/empty.html`
- Create: `apps/api/tests/adapters/rentals_ca/test_html_parser.py`
- Modify: `apps/api/pyproject.toml` (add `selectolax`)

- [ ] **Step 1: Add `selectolax` dependency and sync**

In `apps/api/pyproject.toml`, append to `dependencies`:

```toml
"selectolax>=0.3.21",
```

Run:

```bash
cd apps/api
uv sync --extra dev
```

- [ ] **Step 2: Write the recorder script**

```python
# apps/api/scripts/record_rentals_ca_fixture.py
"""One-off: record real rentals.ca search HTML to use as a test fixture.

Run this MANUALLY (not in CI) to refresh fixtures when the site's DOM changes.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from rentwise.adapters.playwright_fetcher import PlaywrightFetcher
from rentwise.settings import settings

OUT = Path(__file__).resolve().parent.parent / "tests/fixtures/rentals_ca/sample_listings.html"


async def main() -> int:
    fetcher = PlaywrightFetcher(user_agent=settings.user_agent)
    try:
        html = await fetcher.fetch_html(
            "https://rentals.ca/vancouver?beds_min=2", wait_for="body"
        )
    finally:
        await fetcher.close()
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {len(html):,} bytes to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

Run it once to capture the live HTML:

```bash
cd apps/api
uv run python -m playwright install chromium  # only needed once
uv run python scripts/record_rentals_ca_fixture.py
```

If `record_rentals_ca_fixture.py` fails because TOS verification (Task 0) returned PROHIBITED, **stop here**.

- [ ] **Step 3: Inspect the recorded HTML and identify selectors**

Open `tests/fixtures/rentals_ca/sample_listings.html` in a browser dev tools or text editor. Identify the CSS selector for individual listing cards and, within each card, the selectors for: title, price, bedrooms, address, listing URL, source-listing-id (often in the URL or `data-id` attribute).

Document the observed selectors at the top of `html_parser.py` (Step 5). Selectors below are **placeholders** — replace with the actual values.

- [ ] **Step 4: Write empty.html fixture**

```bash
echo '<html><body><main><div class="no-results">No listings</div></main></body></html>' > tests/fixtures/rentals_ca/empty.html
```

- [ ] **Step 5: Write the failing tests**

```python
# apps/api/tests/adapters/rentals_ca/test_html_parser.py
from pathlib import Path

from rentwise.adapters.rentals_ca.html_parser import parse_listing_cards

FIXTURES = Path(__file__).parent.parent.parent / "fixtures/rentals_ca"


def test_parses_recorded_listings() -> None:
    html = (FIXTURES / "sample_listings.html").read_text(encoding="utf-8")
    listings = parse_listing_cards(html, region="vancouver")
    assert len(listings) > 0
    first = listings[0]
    assert first.source == "rentals_ca"
    assert first.source_url.startswith("https://rentals.ca/")
    assert first.source_listing_id  # non-empty
    assert first.title  # non-empty


def test_empty_results_returns_empty_list() -> None:
    html = (FIXTURES / "empty.html").read_text(encoding="utf-8")
    assert parse_listing_cards(html, region="vancouver") == []


def test_skips_cards_missing_url() -> None:
    """A card without an href is unusable — skip rather than crash."""
    html = '<div class="listing-card"><span class="price">$2000</span></div>'
    assert parse_listing_cards(html, region="vancouver") == []


def test_description_snippet_is_capped() -> None:
    """Per docs/legal.md: snippets ≤200 chars."""
    html = (FIXTURES / "sample_listings.html").read_text(encoding="utf-8")
    for listing in parse_listing_cards(html, region="vancouver"):
        if listing.description_snippet is not None:
            assert len(listing.description_snippet) <= 200
```

- [ ] **Step 6: Run tests to verify they fail**

```bash
uv run pytest tests/adapters/rentals_ca/test_html_parser.py -v
```

Expected: ImportError.

- [ ] **Step 7: Write the implementation**

The selectors below are **placeholders**. After Step 3, edit each `CSS_*` constant to match the observed DOM, then re-run tests.

```python
# apps/api/rentwise/adapters/rentals_ca/html_parser.py
"""Parse Rentals.ca search-result HTML into RawListing objects.

DOM observed YYYY-MM-DD. If selectors break, run scripts/record_rentals_ca_fixture.py
to refresh tests/fixtures/rentals_ca/sample_listings.html, inspect the file,
and update the CSS_* constants below.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urljoin

import structlog
from selectolax.parser import HTMLParser, Node

from rentwise.models import RawListing

log = structlog.get_logger(__name__)

# --- Selectors — update after inspecting recorded fixture ---
CSS_CARD = "[data-listing-id], .listing-card, article[data-id]"
CSS_LINK = "a[href*='/rental/'], a[href*='/listing/']"
CSS_TITLE = "h3, .listing-title"
CSS_PRICE = ".price, [data-price]"
CSS_BEDS = ".beds, [data-beds]"
CSS_ADDRESS = ".address, .listing-address"
CSS_DESC = ".description, .summary"

SNIPPET_MAX = 200
PRICE_RE = re.compile(r"\$?([\d,]+)")
BEDS_RE = re.compile(r"(\d+)")


def _text(node: Node | None) -> str | None:
    if node is None:
        return None
    text = node.text(strip=True) or ""
    return text or None


def _first(card: Node, selector: str) -> Node | None:
    return card.css_first(selector)


def _parse_price(text: str | None) -> int | None:
    if not text:
        return None
    m = PRICE_RE.search(text)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_beds(text: str | None) -> float | None:
    if not text:
        return None
    if "studio" in text.lower() or "bachelor" in text.lower():
        return 0.0
    m = BEDS_RE.search(text)
    return float(m.group(1)) if m else None


def _parse_card(card: Node, *, region: str) -> RawListing | None:
    link = _first(card, CSS_LINK)
    href = link.attributes.get("href") if link else None
    if not href:
        return None
    source_url = urljoin(f"https://rentals.ca/{region}", href)
    listing_id = (
        card.attributes.get("data-listing-id")
        or card.attributes.get("data-id")
        or source_url.rstrip("/").split("/")[-1]
    )
    title = _text(_first(card, CSS_TITLE)) or ""
    price = _parse_price(_text(_first(card, CSS_PRICE)))
    beds = _parse_beds(_text(_first(card, CSS_BEDS)))
    address = _text(_first(card, CSS_ADDRESS))
    desc = _text(_first(card, CSS_DESC))
    snippet = desc[:SNIPPET_MAX] if desc else None

    return RawListing(
        source="rentals_ca",
        source_url=source_url,
        source_listing_id=str(listing_id),
        title=title,
        address=address,
        bedrooms=beds,
        price_cad=price,
        description_snippet=snippet,
        posted_at=datetime.now(UTC),
        raw_metadata={},
    )


def parse_listing_cards(html: str, *, region: str) -> list[RawListing]:
    """Parse the rendered Rentals.ca search results page."""
    tree = HTMLParser(html)
    out: list[RawListing] = []
    for card in tree.css(CSS_CARD):
        try:
            listing = _parse_card(card, region=region)
        except Exception as exc:
            log.warning("rentals_ca.parse_card.failed", error=str(exc))
            continue
        if listing is not None:
            out.append(listing)
    return out
```

- [ ] **Step 8: Iterate selectors against the recorded fixture**

Run the tests:

```bash
uv run pytest tests/adapters/rentals_ca/test_html_parser.py -v
```

If `test_parses_recorded_listings` fails with `len(listings) == 0`, the selectors don't match the live DOM. Open the fixture, inspect, update the `CSS_*` constants, re-run. Repeat until all four tests pass.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml uv.lock \
  rentwise/adapters/rentals_ca/html_parser.py \
  scripts/record_rentals_ca_fixture.py \
  tests/fixtures/rentals_ca/ \
  tests/adapters/rentals_ca/test_html_parser.py
git commit -m "feat(api): rentals.ca html parser + recorded fixture (#13)"
```

---

## Task 4 — `RentalsCaAdapter`

Adapter that satisfies the `SourceAdapter` Protocol by composing `PlaywrightFetcher` + `build_search_url` + `parse_listing_cards`.

**Files:**
- Create: `apps/api/rentwise/adapters/rentals_ca/adapter.py`
- Create: `apps/api/tests/adapters/rentals_ca/test_adapter.py`

- [ ] **Step 1: Write the failing tests**

```python
# apps/api/tests/adapters/rentals_ca/test_adapter.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from rentwise.adapters.base import SourceAdapter
from rentwise.adapters.rentals_ca.adapter import RentalsCaAdapter
from rentwise.models import NormalizedQuery

FIXTURES = Path(__file__).parent.parent.parent / "fixtures/rentals_ca"


def test_satisfies_protocol() -> None:
    adapter = RentalsCaAdapter(region="vancouver", user_agent="RentWise/test")
    assert isinstance(adapter, SourceAdapter)
    assert adapter.name == "rentals_ca"
    assert adapter.method == "browser"
    assert adapter.rate_limit_per_second <= 1.0


async def test_search_yields_parsed_listings() -> None:
    adapter = RentalsCaAdapter(region="vancouver", user_agent="RentWise/test")
    html = (FIXTURES / "sample_listings.html").read_text(encoding="utf-8")
    adapter.fetcher.fetch_html = AsyncMock(return_value=html)

    listings = [r async for r in adapter.search(NormalizedQuery(bedrooms_min=2))]
    assert len(listings) > 0
    adapter.fetcher.fetch_html.assert_awaited_once()
    called_url = adapter.fetcher.fetch_html.await_args.args[0]
    assert called_url.startswith("https://rentals.ca/vancouver")
    assert "beds_min=2" in called_url


async def test_search_dedupes_by_source_listing_id() -> None:
    adapter = RentalsCaAdapter(region="vancouver", user_agent="RentWise/test")
    html = (FIXTURES / "sample_listings.html").read_text(encoding="utf-8")
    # Concatenate the same HTML twice → duplicate IDs
    adapter.fetcher.fetch_html = AsyncMock(return_value=html + html)

    listings = [r async for r in adapter.search(NormalizedQuery())]
    ids = [r.source_listing_id for r in listings]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("status", ["ok", "blocked"])
async def test_health_check_classifies(status: str) -> None:
    adapter = RentalsCaAdapter(region="vancouver", user_agent="RentWise/test")
    if status == "ok":
        adapter.fetcher.fetch_html = AsyncMock(return_value="<html><body>ok</body></html>")
    else:
        from rentwise.adapters.base import RobotsDisallowedError

        adapter.fetcher.fetch_html = AsyncMock(side_effect=RobotsDisallowedError("nope"))

    health = await adapter.health_check()
    assert health.name == "rentals_ca"
    assert health.status == status
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/adapters/rentals_ca/test_adapter.py -v
```

Expected: ImportError.

- [ ] **Step 3: Write the implementation**

```python
# apps/api/rentwise/adapters/rentals_ca/adapter.py
"""Rentals.ca browser-based adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import ClassVar, Literal

import structlog

from rentwise.adapters.base import (
    AdapterCapabilities,
    RobotsDisallowedError,
    SourceAdapter,
)
from rentwise.adapters.playwright_fetcher import PlaywrightFetcher
from rentwise.adapters.rentals_ca.html_parser import parse_listing_cards
from rentwise.adapters.rentals_ca.url_builder import build_search_url
from rentwise.models import AdapterHealth, NormalizedQuery, RawListing

log = structlog.get_logger(__name__)


class RentalsCaAdapter:
    name = "rentals_ca"
    method: Literal["api", "rss", "browser"] = "browser"
    rate_limit_per_second: float = 1.0
    _capabilities: ClassVar[AdapterCapabilities] = {
        "supported_filters": {
            "bedrooms_min",
            "price_min",
            "price_max",
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
        self.base_url = f"https://rentals.ca/{region}"
        self.user_agent = user_agent
        self.capabilities: AdapterCapabilities = self._capabilities
        self.fetcher = PlaywrightFetcher(user_agent=user_agent, jitter_ms=jitter_ms)

    async def search(self, query: NormalizedQuery) -> AsyncIterator[RawListing]:
        url = build_search_url(query, region=self.region)
        html = await self.fetcher.fetch_html(url, wait_for="body")
        seen: set[str] = set()
        for raw in parse_listing_cards(html, region=self.region):
            if raw.source_listing_id in seen:
                continue
            seen.add(raw.source_listing_id)
            yield raw

    async def fetch_listing(self, listing_id: str) -> RawListing | None:
        # Rentals.ca individual listing fetch — not implemented this phase.
        return None

    async def health_check(self) -> AdapterHealth:
        try:
            await self.fetcher.fetch_html(self.base_url, wait_for="body")
            return AdapterHealth(name=self.name, status="ok")
        except RobotsDisallowedError:
            return AdapterHealth(name=self.name, status="blocked", last_error="robots.txt")
        except Exception as exc:
            return AdapterHealth(name=self.name, status="degraded", last_error=str(exc))


# Type assertion: instances satisfy the Protocol
_: SourceAdapter = RentalsCaAdapter(region="vancouver", user_agent="RentWise/0.1")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/adapters/rentals_ca/ -v
```

Expected: all green (URL builder + parser + adapter tests).

- [ ] **Step 5: Commit**

```bash
git add rentwise/adapters/rentals_ca/adapter.py tests/adapters/rentals_ca/test_adapter.py
git commit -m "feat(api): RentalsCaAdapter wiring fetcher + parser (#13)"
```

---

## Task 5 — Wire adapter into search router + settings

Register the adapter so `/search` uses it alongside Craigslist.

**Files:**
- Modify: `apps/api/rentwise/settings.py`
- Modify: `apps/api/rentwise/http/search.py:17-27`
- Modify: `apps/api/tests/http/test_search.py` (verify aggregation)

- [ ] **Step 1: Add settings entry**

Edit `apps/api/rentwise/settings.py`. After the `craigslist_region` field, add:

```python
    rentals_ca_region: str = Field(
        default="vancouver",
        validation_alias="RENTWISE_RENTALS_CA_REGION",
    )
```

- [ ] **Step 2: Register the adapter**

Edit `apps/api/rentwise/http/search.py:17-27`:

```python
@lru_cache(maxsize=1)
def _build_adapters() -> tuple[SourceAdapter, ...]:
    """Build adapter instances once per process so rate-limit state is shared."""
    from rentwise.adapters.craigslist.adapter import CraigslistAdapter
    from rentwise.adapters.rentals_ca.adapter import RentalsCaAdapter

    return (
        CraigslistAdapter(
            region=settings.craigslist_region,
            user_agent=settings.user_agent,
        ),
        RentalsCaAdapter(
            region=settings.rentals_ca_region,
            user_agent=settings.user_agent,
        ),
    )
```

- [ ] **Step 3: Add an integration test**

Edit `apps/api/tests/http/test_search.py`. Add (don't replace existing tests):

```python
async def test_search_aggregates_craigslist_and_rentals_ca(
    client, monkeypatch, sample_normalized_query
) -> None:
    """`/search` returns listings from both adapters when both succeed."""
    from rentwise.adapters.craigslist.adapter import CraigslistAdapter
    from rentwise.adapters.rentals_ca.adapter import RentalsCaAdapter

    # Stub each adapter's `search` to yield one fake listing each
    async def fake_cl_search(query):
        from rentwise.models import RawListing
        from datetime import UTC, datetime

        yield RawListing(
            source="craigslist",
            source_url="https://example.test/cl/1",
            source_listing_id="cl-1",
            title="CL listing",
            posted_at=datetime.now(UTC),
            raw_metadata={},
        )

    async def fake_rc_search(query):
        from rentwise.models import RawListing
        from datetime import UTC, datetime

        yield RawListing(
            source="rentals_ca",
            source_url="https://rentals.ca/vancouver/1",
            source_listing_id="rc-1",
            title="RC listing",
            posted_at=datetime.now(UTC),
            raw_metadata={},
        )

    monkeypatch.setattr(CraigslistAdapter, "search", fake_cl_search)
    monkeypatch.setattr(RentalsCaAdapter, "search", fake_rc_search)

    resp = await client.post("/search", json={"query": sample_normalized_query})
    assert resp.status_code == 200
    body = resp.json()
    sources = {l["source"] for l in body["listings"]}
    assert sources == {"craigslist", "rentals_ca"}
```

If `tests/http/test_search.py` already has its own adapter-stubbing pattern, adapt to match it instead of importing directly. Inspect the existing file before adding the test.

- [ ] **Step 4: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all pre-existing tests still green + the new integration test passes.

- [ ] **Step 5: Lint + format**

```bash
uv run ruff check .
uv run ruff format .
```

- [ ] **Step 6: Commit**

```bash
git add rentwise/settings.py rentwise/http/search.py tests/http/test_search.py
git commit -m "feat(api): register rentals.ca adapter in /search aggregation (#13)"
```

---

## Task 6 — Docs + roadmap + close issue

**Files:**
- Modify: `docs/roadmap.md` (Phase 3 checkboxes)
- Modify: `README.md` (source list)
- Modify: `docs/legal.md` (already updated in Task 0; verify still current)

- [ ] **Step 1: Tick Phase 3 boxes in `docs/roadmap.md`**

Change `- [ ] Playwright adapter base class` → `- [x] Playwright adapter base class`.
Change `- [ ] Rentals.ca` → `- [x] Rentals.ca` under "Implement adapters in this order".

- [ ] **Step 2: Add Rentals.ca to README source list**

In the README's source list, add a Rentals.ca line.

- [ ] **Step 3: Commit docs**

```bash
git add docs/roadmap.md README.md
git commit -m "docs: tick Phase 3 (Playwright base + Rentals.ca) (#13)"
```

- [ ] **Step 4: Push branch + open PR**

```bash
git push origin feat/phase-3-playwright-rentals-ca
gh pr create --title "feat(api): Playwright adapter base + Rentals.ca adapter (#13)" --body "Closes #13. ..."
```

PR body should include: TOS-verification outcome (link to the legal.md commit), screenshot of `/search` returning both sources, link to passing CI.

- [ ] **Step 5: After merge, close issue #13** (or auto-close via "Closes #13" in PR body).

---

## Self-review checklist (run before handing off)

- ✅ Spec coverage: TOS verification (Task 0), Playwright base (Task 1), Rentals.ca URL (Task 2), parser (Task 3), adapter (Task 4), wiring (Task 5), docs (Task 6) — all five issue requirements covered.
- ✅ No placeholders for code: every code block has full, runnable contents (selectors are documented as placeholders requiring manual inspection in Task 3, with the iteration loop spelled out).
- ✅ Type consistency: `PlaywrightFetcher.fetch_html(url, *, wait_for=None)` is the same signature in Task 1, used in Task 3 (recorder), and Task 4 (adapter `search` and `health_check`). `parse_listing_cards(html, *, region)` is the same signature in Task 3 tests, impl, and Task 4 adapter.
- ✅ Branch decision documented for Task 0 PROHIBITED outcome.
