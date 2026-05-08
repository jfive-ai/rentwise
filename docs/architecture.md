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
  - `aggregator/` — Orchestrates per-source adapter calls, post-filter (school catchment, transit walk), search-cache freshness
  - `adapters/` — One module per source. Today: Craigslist (RSS) + Playwright base. Phase 8 PR-C/D/E adds direct adapters for Rentals.ca, PadMapper, Zumper, REW.ca, and liv.rent (each subject to `docs/operational-rules.md`).
  - `enrichment/` — Address normalization (`pyap`), geocoding (Nominatim) with persistent cache, school catchment lookup (VSB GeoJSON via `shapely`), transit lookup (TransLink slim stops, haversine + 5 km/h), photo perceptual hashing (`imagehash.phash`).
  - `dedup/` — Cross-source duplicate scoring (additive weights: address, price, photo phash, bedrooms; threshold 0.7). Assigns shared `canonical_id`.
  - `notifications/` — APScheduler `AsyncIOScheduler` (one job per saved search), SMTP notifier over stdlib `smtplib`, web push notifier (`pywebpush` + VAPID), alert runner with dedup ledger so the same listing doesn't notify twice.
  - `storage/` — SQLite (FTS5 + Alembic migrations; current head `0010_drop_capture`). Tables: listings, canonical_listings, searches, source_health, geocode_cache, photo_hash_cache, alert_log, llm_settings, web_push_subscriptions. The Phase 3 `captures` table was dropped in `0010` when the browser extension was retired in Phase 8 PR-B.
  - `http/` — FastAPI routers:
    - `search.py` — `POST /search` (aggregator entrypoint).
    - `searches.py` — saved-search CRUD + `POST /searches/{cache_key}/run-now`.
    - `web_push.py` — `GET /notifications/web-push/public-key` + subscription CRUD (Phase 5 PR-C).
    - `map_overlays.py` — school-catchment + SkyTrain GeoJSON for the Phase 7 PR-B overlays.
    - `/settings/llm` + `/health` + `/health/llm` + `/translate-query` are wired directly in `main.py`.

### 3. Browser extension — retired in Phase 8 PR-B
The Phase 3 Chrome MV3 extension that read listings from pages the user already had open is no longer part of the system. The five sources it covered (Rentals.ca, PadMapper, Zumper, REW.ca, liv.rent) are now picked up by direct server-side adapters in PR-C/D/E. Facebook Marketplace, the sixth, is out of scope because we never automate logins. The historical Phase 3 design lives in `docs/roadmap.md`.

### 4. Desktop shell (`apps/desktop/`)
A 60-line Electron `main.js` + `package.json` that loads the static Expo web export from `apps/web/dist/index.html`, intercepts `http(s)://` navigations / window-opens to defer to the user's default browser, and exposes nothing else (no preload, no node integration in the renderer, sandbox on). Built via `./scripts/build-mac.sh`, which runs `expo export -p web` and then `electron-builder --mac --arm64 --dir`. The macOS app expects the FastAPI backend at the URL configured in `apps/web/app.json` (`extra.apiBaseUrl`, default `http://localhost:8000`) — Electron does not bundle Python.

The Phase 8 PR-A choice of Electron over Mac Catalyst is deliberate: `expo run:ios --device "Mac"` produced a "Designed for iPad" iOS-platform `.app` Finder refused to launch ("incorrect executable format"). True Mac Catalyst would require enabling `SUPPORTS_MACCATALYST=YES` in the Pods project plus re-jigging hermes-engine and several pods that don't ship Catalyst-compatible binaries — far past the issue's "lightest lift" remit.

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

For sources without APIs/RSS, we use Playwright in headless mode behind two shared modules:

- `adapters/playwright_fetcher.py` — composes a `PlaywrightFetcher` with the per-origin `RobotsCache` and a token-bucket `RateLimitedFetcher`. Every fetch re-checks `robots.txt` and waits for the bucket; jitter is added on top.
- `adapters/scaffold_base.py` — `ScaffoldAdapterBase`, the shared shape for the Phase 8 PR-E direct adapters (Zumper, REW.ca, liv.rent). Subclasses only declare `name`, `base_url`, a `_search_url(query)` builder, and an `_extract(html, query)` step. Init-time robots checks fail loudly via `health_check` rather than silently on first use; `rate_limit_per_second` is capped at `0.5` for these scaffolds (half the platform-wide ceiling, since their TOS language is stricter than Craigslist's).

A typical adapter looks like:

```python
class PlaywrightAdapter:
    async def search(self, query):
        html = await self.fetcher.fetch(self._build_search_url(query))
        for raw in self._extract(html, query):
            yield raw
```

`PadMapperAdapter` and `RentalsCaAdapter` are richer because each enforces site-specific in-process guards on top of `urllib.robotparser` (which doesn't reliably parse `Disallow: /*box=*` style wildcards). `RentalsCaAdapter` additionally maintains an explicit allow-list of query parameters in its URL builder so we never accidentally include a `bbox=` / `amenities=` / `types=` param the site disallows.

The Phase 8 PR-E adapters (`zumper`, `rew`, `livrent`) ship with stub `_extract` methods that return `[]` and log `<adapter>.selectors_not_yet_calibrated` — opting them in via env vars makes them appear in `_build_adapters()` but does not produce listings until the per-site selectors are filled in. This is intentional: we'd rather ship a documented stub than fake coverage.

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

**MVP: SQLite** with FTS5 for full-text search. Migrations live under `apps/api/alembic/versions/` (current head `0010_drop_capture`).

Tables:
- `listings` — one row per source listing
- `canonical_listings` — deduplicated groups
- `searches` — saved searches (label + alert metadata, Phase 5 PR-A)
- `alert_log` — sent notifications (alert dedup ledger, Phase 5 PR-B)
- `web_push_subscriptions` — registered browser endpoints (Phase 5 PR-C)
- `source_health` — adapter status tracking
- `geocode_cache` — Nominatim results, TTL'd (Phase 4 PR-A)
- `photo_hash_cache` — perceptual hashes per photo URL (Phase 4 PR-C)
- `llm_settings` — encrypted per-user LLM config (Phase 2)

Single-user self-hosted MVP, so there is no `users` table. The retired Phase 3 `captures` table was dropped in migration `0010_drop_capture`.

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

For a personal-use macOS install, `./scripts/build-mac.sh` wraps the Expo web export in the Electron shell at `apps/desktop/` and emits `apps/desktop/build/mac-arm64/RentWise.app` (`--install` copies it to `/Applications/`). The `.app` is unsigned; first launch needs `right-click → Open → Open Anyway` once. Listing links open in the user's default browser, not inside the Electron window. The `.app` does not bundle Python — `make dev` or `docker compose up` still has to be running for the API at `http://localhost:8000` (override via `extra.apiBaseUrl` in `apps/web/app.json`).

## Future Considerations

- **Multi-user mode**: Add auth (Auth.js or similar), per-user encrypted credentials.
- **Mobile push**: Expo Push Notifications for iOS/Android (web push covers desktop browsers + the Electron shell today).
- **Native macOS app**: revisit Mac Catalyst once Expo + RN ship Catalyst-compatible Pods, or rebuild the shell in Tauri to drop the Electron runtime weight. The current Electron shell at `apps/desktop/` is the explicit Phase 8 PR-A choice — see the desktop-shell section above.
- **Federation**: Multiple users could optionally share dedup signals (without sharing private data) to improve dedup quality across instances.
