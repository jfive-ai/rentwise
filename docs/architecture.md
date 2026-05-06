# Architecture

## System Components

### 1. Frontend (`apps/web`)
- **Tech:** React + Expo (Universal — runs on web, iOS, macOS)
- **Why Expo:** Single codebase for all three targets. Cleaner than maintaining separate Next.js + SwiftUI codebases.
- **Key views:**
  - **Search interface (dual-mode):**
    - NL search bar with parsed-query preview (editable chips)
    - Filter panel with full faceted controls (bedrooms, price, neighborhood, etc.)
    - One-click toggle between modes; both share the same `NormalizedQuery` state
  - **Results display (four view modes, switchable):**
    - Card grid (default for tablet/desktop)
    - List/table (sortable columns, virtualized for large result sets)
    - Map (MapLibre GL JS + clustering, with school catchment overlays)
    - Split view (map + list, synced highlighting — default on wide screens)
  - Listing detail (with link out to source)
  - Saved searches & alerts management
  - Settings (LLM provider, API keys, source preferences, notification config)

#### Shared State Model
Both search modes operate on the same in-memory query object:

```typescript
type NormalizedQuery = {
  bedroomsMin?: number;
  bedroomsMax?: number;
  priceMin?: number;
  priceMax?: number;
  neighborhoods: string[];
  schoolCatchment?: string;
  pets?: 'required' | 'ok' | 'no' | 'any';
  furnished?: boolean;
  availableAfter?: string;
  transitMaxWalkMinutes?: number;
  freeTextKeywords: string[];
};

// Source of truth — both NL parse and filter UI write here
const [query, setQuery] = useState<NormalizedQuery>({});
```

NL mode calls `POST /api/translate-query` and sets the result. Filter mode mutates `query` directly. Both then call `POST /api/search` with the same payload.

### 2. Backend (`apps/api`)
- **Tech:** Python 3.12 + FastAPI + Uvicorn
- **Why Python:** Best ecosystem for Playwright, LLM SDKs, and data parsing.
- **Modules:**
  - `llm/` — LiteLLM client wrapper, settings, fallback handling
  - `query_translator/` — LLM-powered NL → structured query (provider-agnostic via LiteLLM)
  - `aggregator/` — Orchestrates parallel adapter calls, dedup, ranking
  - `adapters/` — One module per source (livrent, padmapper, etc.)
  - `enrichment/` — School catchment, transit, walkscore
  - `storage/` — SQLite + FTS5
  - `scheduler/` — APScheduler for saved-search refresh
  - `notifier/` — Email (SMTP) + push (APNs/web push) for alerts

### 3. Browser Extension (`apps/extension`) — for Facebook Marketplace only
- **Tech:** Plain JS/TS, manifest v3
- **Function:** Extracts listings from pages the user personally browses on Facebook Marketplace, sends them to the local API.

## Data Flow

There are two entry paths, but they converge into the same aggregation pipeline:

```
                    ┌─────────────────────────────────────────────┐
                    │ User chooses: NL input or Filter UI         │
                    └────────┬───────────────────┬────────────────┘
                             │                   │
              "2br Kits      │                   │   ┌─────────────┐
              under $3000"   │                   │   │ Filter form │
              (or Korean:    │                   │   │ • Bedrooms  │
              "키츠에 2베드   │                   │   │ • Price     │
              3000불 이하")  │                   │   │ • Pets      │
                             │                   │   │ • etc.      │
                             ▼                   │   └──────┬──────┘
                    ┌──────────────────┐         │          │
                    │ POST /translate  │         │          │
                    │ → LiteLLM → LLM  │         │          │
                    └────────┬─────────┘         │          │
                             │                   │          │
                             ▼                   │          │
                    ┌──────────────────┐         │          │
                    │ Editable chips   │ ◀──────┘          │
                    │ preview          │                    │
                    └────────┬─────────┘                    │
                             │                              │
                             └──────────────┬───────────────┘
                                            │
                                            ▼
                              ┌──────────────────────────┐
                              │ NormalizedQuery object   │
                              └─────────────┬────────────┘
                                            │
                                            ▼
                              ┌──────────────────────────┐
                              │ POST /search             │
                              │ aggregator.search(query) │
                              └─────────────┬────────────┘
                                            │
       ┌─────────────────┬──────────────────┼──────────────────┬──────────────┐
       ▼                 ▼                  ▼                  ▼              ▼
┌──────────────┐  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ adapters.    │  │ adapters.   │  │ adapters.    │  │ adapters.    │  │ adapters.    │
│ livrent      │  │ padmapper   │  │ rentals_ca   │  │ rew          │  │ craigslist   │
└──────┬───────┘  └──────┬──────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       └─────────────────┴──────────────────┼─────────────────┴─────────────────┘
                                            │
                                            ▼
                              ┌──────────────────────────┐
                              │ dedup → rank → enrich    │
                              │ → store → stream to UI   │
                              └──────────────────────────┘
```

The key insight: **the LLM only runs on the NL path**. Filter-mode searches skip the LLM entirely (faster, no API cost), but produce the exact same query object the LLM would have produced. This makes filter mode a reliable fallback when the LLM is down or rate-limited.

## Adapter Interface

All adapters implement a uniform Protocol:

```python
from typing import Protocol, AsyncIterator

class SourceAdapter(Protocol):
    name: str
    base_url: str
    method: Literal["api", "rss", "browser"]
    rate_limit_per_second: float = 1.0

    async def search(self, query: NormalizedQuery) -> AsyncIterator[RawListing]:
        """Yield listings as they are found. Respect rate limits."""
        ...

    async def fetch_listing(self, listing_id: str) -> RawListing | None:
        """Fetch a single listing by source-specific ID."""
        ...

    async def health_check(self) -> AdapterHealth:
        """Return status: ok / degraded / blocked."""
        ...
```

This makes it trivial to add new sources without touching the aggregator.

## Browser Adapter Pattern

For sources without APIs/RSS, we use Playwright in headless mode:

```python
class PlaywrightAdapter:
    async def search(self, query):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(
                user_agent=USER_AGENT,
                # Reuse a single browser context per session for efficiency
            )
            await self._respect_robots_txt(query.url)
            await asyncio.sleep(random.uniform(0.5, 1.5))  # jitter
            page = await ctx.new_page()
            await page.goto(self._build_search_url(query))
            # ... extract listings
            await browser.close()
```

Each adapter has a "selector map" file that's easy to update when a site's HTML changes:

```yaml
# adapters/padmapper/selectors.yaml
list_container: "div[data-test='search-results']"
listing_card: "article[data-test='listing-card']"
fields:
  price: ".price-text"
  bedrooms: "[data-test='beds']"
  address: "[data-test='address']"
```

## LLM Query Translation

We use **LiteLLM** to abstract over any LLM provider. The user picks their model (free OpenRouter, Claude, GPT, Gemini, or local Ollama) at first run or via the settings UI.

For reliable parsing, we use **structured output via tool use** — supported across all major providers:

```python
TOOL = {
    "name": "submit_query",
    "description": "Submit a parsed rental search query",
    "input_schema": {
        "type": "object",
        "properties": {
            "bedrooms_min": {"type": "number"},
            "bedrooms_max": {"type": "number"},
            "price_min": {"type": "integer"},
            "price_max": {"type": "integer"},
            "neighborhoods": {"type": "array", "items": {"type": "string"}},
            "school_catchment": {"type": "string"},
            "pets": {"type": "string", "enum": ["required", "ok", "no", "any"]},
            "furnished": {"type": "boolean"},
            "available_after": {"type": "string", "format": "date"},
            "transit_max_walk_minutes": {"type": "integer"},
            "free_text_keywords": {"type": "array", "items": {"type": "string"}}
        }
    }
}
```

The system prompt is **bilingual (Korean + English)** and teaches the LLM about Vancouver-specific neighborhoods, school catchments, and SkyTrain stations, so it can recognize "Kits", "키츠", "Lord Byng catchment", "롯바잉 학군", "near 99 B-Line", "99번 버스 근처", etc.

See [llm-providers.md](llm-providers.md) for the full LLM strategy and configuration.

## Storage

**MVP: SQLite** with FTS5 for full-text search.

Tables:
- `listings` — one row per source listing
- `canonical_listings` — deduplicated groups
- `searches` — saved searches
- `alerts` — sent notifications (for dedup)
- `users` — single user for self-hosted MVP
- `source_health` — adapter status tracking

**Scaling path:** PostgreSQL + Meilisearch when we hit ~50k active listings or multi-user.

## Deployment (MVP)

Self-hosted via Docker Compose:

```yaml
services:
  api:
    build: ./apps/api
    ports: ["8000:8000"]
    volumes: ["./data:/data"]
  web:
    build: ./apps/web
    ports: ["3000:3000"]
```

Single `docker-compose up` and it runs locally.

## Future Considerations

- **Multi-user mode**: Add auth (Auth.js or similar), per-user encrypted credentials for Facebook session.
- **Mobile push**: Expo Push Notifications for iOS/Android.
- **macOS native menu bar app**: Use Tauri or Electron wrapper around the web app.
- **Federation**: Multiple users could optionally share dedup signals (without sharing private data) to improve dedup quality across instances.
