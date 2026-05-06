# Phase 1 — Craigslist End-to-End: Design Spec

**Date:** 2026-05-06
**Scope:** Phase 1 of `docs/roadmap.md` — first adapter (Craigslist via RSS), storage, aggregator, `/search` API, filter UI, dual results display.
**Out of scope:** NL search (Phase 2), multi-source (Phase 3), dedup/enrichment (Phase 4), saved searches/alerts (Phase 5), map view (Phase 7), native builds (Phase 8).

## 1. Goals & Non-Goals

### Goals
- Replace the `/search` stub with a working endpoint backed by SQLite that returns Craigslist Vancouver listings filtered by a `NormalizedQuery`.
- Ship the full faceted filter UI (Mode B per `docs/specifications.md` § 3.1) — controls without backend support are visibly disabled with a roadmap badge.
- Ship card-grid + list/table results display (per § 3.2) with sort, view switching, and per-card local actions.
- Establish patterns the rest of Phase 1+ will follow: adapter capabilities declaration, async ORM repos, structured error responses, recorded fixtures for tests.

### Non-Goals
- Natural-language search input. The data model and query shape support it, but no NL UI ships in Phase 1.
- Server-side persistence of save/hide/contacted state (local-only via storage abstraction; server in Phase 5).
- Map view / split view / PWA / mobile-responsive polish.
- Background scheduler — first-time / cache-miss queries pull live; saved-search refresh is Phase 5.

## 2. PR Sequencing

Two PRs against `main`:

1. **PR-1 — backend** (`feat/phase-1-backend`): chunks 1–4 from the roadmap. Must merge before PR-2.
2. **PR-2 — frontend** (`feat/phase-1-frontend`): chunks 5–6. Blocked on PR-1.

GitHub tracking issues mirror this split.

## 3. Architecture

### 3.1 Module layout (new + extended)

```
apps/api/rentwise/
  adapters/
    base.py                  # extended: AdapterCapabilities TypedDict + Protocol field
    craigslist/
      __init__.py
      adapter.py             # CraigslistAdapter implementing SourceAdapter
      rss_parser.py          # feedparser entry → RawListing
      title_parser.py        # regex extraction: price, beds, sqft, neighborhood
      url_builder.py         # NormalizedQuery → CL search URL (supported filters only)
      neighborhoods.py       # NEIGHBORHOOD_POSTAL_SEEDS dict
  aggregator/
    __init__.py
    service.py               # AggregatorService.search() — orchestration entry point
    freshness.py             # cache_key, TTL math, canonical query JSON
  storage/
    __init__.py
    db.py                    # async SQLAlchemy engine + session factory
    models.py                # SQLAlchemy ORM (separate from Pydantic)
    repositories.py          # ListingRepo, SearchRepo, SourceHealthRepo
  http/
    __init__.py
    search.py                # /search router (replaces stub in main.py)
  alembic/
    env.py
    versions/
      0001_initial.py        # creates all Phase 1 tables + FTS5 + triggers
```

```
apps/web/
  app/
    _layout.tsx              # extended: wrap in QueryProvider
    index.tsx                # SearchScreen (replaces system-status home)
  src/
    query/
      QueryProvider.tsx      # React Context: NormalizedQuery + setter
      useQuery.ts
      types.ts               # mirrors Pydantic NormalizedQuery
    search/
      SearchScreen.tsx
      api.ts                 # POST /search wrapper
      useSearch.ts           # loading/error states, debounce
    filters/
      FilterPanel.tsx
      BedroomsControl.tsx
      PriceRangeControl.tsx
      NeighborhoodControl.tsx
      KeywordsControl.tsx
      DisabledControl.tsx    # wraps unsupported controls with roadmap badge
    results/
      ResultsToolbar.tsx
      CardGrid.tsx
      ListingCard.tsx
      ListTable.tsx
      ListingRow.tsx
      PerCardActions.tsx
      EmptyState.tsx
      ErrorState.tsx
      LoadingState.tsx
    storage/
      listingActions.ts      # save/hide/contacted — AsyncStorage on native,
                             # localStorage on web, single interface
```

### 3.2 Adapter capability declaration

Adapters declare which `NormalizedQuery` fields they honor; the aggregator strips unsupported fields before dispatch and surfaces them in the response.

```python
# adapters/base.py
class AdapterCapabilities(TypedDict):
    supported_filters: set[Literal[
        "bedrooms_min", "bedrooms_max",
        "price_min", "price_max",
        "neighborhoods",
        "free_text_keywords",
        # extended in later phases:
        # "school_catchment", "pets", "furnished",
        # "available_after", "transit_max_walk_minutes",
    ]]

class SourceAdapter(Protocol):
    name: str
    base_url: str
    method: Literal["api", "rss", "browser"]
    rate_limit_per_second: float
    capabilities: AdapterCapabilities

    async def search(self, query: NormalizedQuery) -> AsyncIterator[RawListing]: ...
    async def fetch_listing(self, listing_id: str) -> RawListing | None: ...
    async def health_check(self) -> AdapterHealth: ...
```

`CraigslistAdapter.capabilities.supported_filters = {"bedrooms_min", "bedrooms_max", "price_min", "price_max", "neighborhoods", "free_text_keywords"}`.

## 4. Data Flow

```
client → POST /search { query: NormalizedQuery, force_refresh?: bool, limit?, offset?, sort? }
  │
  ▼
SearchRouter.search()
  │
  ▼
AggregatorService.search(query, force_refresh)
  │
  ├─ 1. cache_key = hash(canonical_json(query))
  │
  ├─ 2. lookup searches table by cache_key
  │     ├─ hit & age < TTL & !force_refresh → load listings → return
  │     └─ miss / stale / forced ↓
  │
  ├─ 3. for each registered adapter:
  │       a. project query → adapter.capabilities.supported_filters
  │       b. await adapter.search(projected_query) → AsyncIterator[RawListing]
  │       c. normalize → NormalizedListing
  │       d. within-source dedup by source_listing_id
  │
  ├─ 4. persist: INSERT OR REPLACE into listings;
  │              UPSERT into searches; bump source_health
  │
  └─ 5. return SearchResponse {
           listings, total, cache_status, unsupported_filters, source_health
         }
```

### 4.1 Freshness

- Cache TTL: `RENTWISE_SEARCH_CACHE_TTL_SECONDS` (default 900 = 15 min).
- `force_refresh=true` bypasses cache.
- Cache miss does live fetch synchronously. Latency target: < 8s p95 for live CL.
- Phase 5 seam: `searches` table already stores `cache_key + query_json + last_run_at + is_saved`, ready for APScheduler.

### 4.2 Pagination & sort

- `limit` default 50, max 200; `offset`-based pagination.
- `sort` enum: `newest` (default), `price_asc`, `price_desc`, `bedrooms`. Server-applied.
- No cursor pagination in Phase 1.

### 4.3 Error model

| Failure | Aggregator behavior | API response |
|---|---|---|
| Adapter raises | Catch, log, mark source `degraded`, continue | 200 OK, `source_health.craigslist="degraded"`, possibly empty `listings` |
| RSS unreachable | Same as above | Same |
| RSS malformed | Log, mark `degraded`, skip | Same |
| DB write fails | 503 — never return stale data unflagged | `{"error":"storage_unavailable"}` |
| Query schema invalid | 422 (FastAPI default) | Standard validation error |

Robots.txt enforcement happens in the adapter base class before any HTTP call. A `RobotsDisallowedError` mirrors the "blocked" status.

## 5. Data Model

### 5.1 Pydantic changes (`apps/api/rentwise/models.py`)

Replace flat `school_catchments: list[str]` with a typed object:

```python
class SchoolCatchments(BaseModel):
    """Per-level Vancouver school catchments. All optional —
    not every area has a middle school (most VSB is K-7 / 8-12).
    """
    elementary: str | None = None    # K-7
    middle: str | None = None        # 8-9 (rare in VSB, common in suburbs)
    secondary: str | None = None     # 8-12 or 10-12

class NormalizedListing(BaseModel):
    ...
    school_catchments: SchoolCatchments = Field(default_factory=SchoolCatchments)
```

`NormalizedQuery.school_catchment: str | None` stays a single string — match against any of the three columns. Adding a level filter is YAGNI for Phase 1.

### 5.2 SQLite schema

```sql
CREATE TABLE listings (
    id                    TEXT PRIMARY KEY,        -- UUIDv4
    canonical_id          TEXT,                    -- nullable until Phase 4
    source                TEXT NOT NULL,           -- "craigslist"
    source_listing_id     TEXT NOT NULL,
    source_url            TEXT NOT NULL,
    title                 TEXT NOT NULL,
    snippet               TEXT,                    -- ≤200 chars (legal.md)
    address_raw           TEXT,
    address_normalized    TEXT,                    -- nullable until Phase 4
    neighborhood          TEXT,
    lat                   REAL,
    lon                   REAL,
    bedrooms              REAL,                    -- 0.5 = studio
    bathrooms             REAL,
    price_cad             INTEGER,
    pets_allowed          INTEGER,                 -- 0/1/NULL
    furnished             INTEGER,                 -- 0/1/NULL
    available_date        TEXT,                    -- ISO date or NULL
    posted_at             TEXT NOT NULL,           -- ISO datetime
    last_seen_at          TEXT NOT NULL,
    catchment_elementary  TEXT,
    catchment_middle      TEXT,
    catchment_secondary   TEXT,
    photo_urls_json       TEXT,                    -- JSON array
    raw_metadata_json     TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    UNIQUE (source, source_listing_id)
);
CREATE INDEX idx_listings_canonical    ON listings(canonical_id);
CREATE INDEX idx_listings_posted_at    ON listings(posted_at DESC);
CREATE INDEX idx_listings_price        ON listings(price_cad);
CREATE INDEX idx_listings_bedrooms     ON listings(bedrooms);
CREATE INDEX idx_listings_catchment_elem ON listings(catchment_elementary);
CREATE INDEX idx_listings_catchment_sec  ON listings(catchment_secondary);

CREATE VIRTUAL TABLE listings_fts USING fts5(
    title, snippet, neighborhood,
    content='listings', content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);
-- + insert/update/delete triggers to keep FTS in sync

CREATE TABLE canonical_listings (
    id                  TEXT PRIMARY KEY,
    primary_listing_id  TEXT NOT NULL REFERENCES listings(id),
    created_at          TEXT NOT NULL
);

CREATE TABLE searches (
    cache_key         TEXT PRIMARY KEY,
    query_json        TEXT NOT NULL,
    last_run_at       TEXT NOT NULL,
    listing_ids_json  TEXT NOT NULL,
    total_count       INTEGER NOT NULL,
    is_saved          INTEGER NOT NULL DEFAULT 0,
    user_label        TEXT
);
CREATE INDEX idx_searches_last_run ON searches(last_run_at);

CREATE TABLE source_health (
    source                TEXT PRIMARY KEY,
    status                TEXT NOT NULL,           -- ok|degraded|blocked
    last_success_at       TEXT,
    last_error_at         TEXT,
    last_error_message    TEXT,
    consecutive_failures  INTEGER NOT NULL DEFAULT 0,
    updated_at            TEXT NOT NULL
);

-- Phase 5 stubs (created empty so migrations don't churn later):
CREATE TABLE alerts (id TEXT PRIMARY KEY);
CREATE TABLE users  (id TEXT PRIMARY KEY);
```

Migration: one Alembic revision creates everything. `alembic upgrade head` runs at container start (entrypoint script) and at dev-server start. Tests use in-memory SQLite + the same migration.

### 5.3 Persistence patterns

- SQLAlchemy 2.x async engine + `aiosqlite`.
- ORM models live in `storage/models.py`, are not exposed to HTTP.
- Repositories own ORM ↔ Pydantic mapping. Routes never touch ORM types.
- Listing IDs: UUIDv4 generated server-side on first ingest. Re-fetches do `INSERT OR REPLACE` matched on `(source, source_listing_id)`, preserving the original `id`.

## 6. Craigslist Adapter

### 6.1 Source

`https://vancouver.craigslist.org/search/apa?format=rss` — the apartments/housing RSS feed. **RSS only.** legal.md prohibits HTML scraping of CL.

### 6.2 URL building

Supported parameters:
- `min_price`, `max_price`
- `min_bedrooms`, `max_bedrooms`
- `postal` + `search_distance` (5km radius), seeded from `NEIGHBORHOOD_POSTAL_SEEDS` (~25 entries: Kitsilano→V6K, East Vancouver→V5L, etc.)
- `query` (free-text keywords)
- `hasPic=1` always

Unknown neighborhoods → dropped from URL, surfaced in `unsupported_filters`. Multi-neighborhood = up to 3 fetches (capped to respect rate limits), results OR'd.

### 6.3 RSS parsing

`feedparser` parses the feed. Each entry → `RawListing | None`:

- `source_listing_id`: extracted from URL (`.../apa/d/.../<id>.html`)
- `source_url`: `entry.link`
- `title`: `entry.title`
- `description_snippet`: `entry.summary` truncated to 200 chars (legal.md)
- `posted_at`: `entry.dc_date` (W3C dublin core)
- `lat` / `lon`: `entry.geo_lat` / `entry.geo_long` when present (~60–70% of posts)
- `price_cad`, `bedrooms`, `sqft_hint`, `neighborhood_hint`: from title parser
- `address`: NOT populated (RSS doesn't carry it; Phase 4 will geocode lat/lon → address)

### 6.4 Title parsing

CL titles look like `"$2500 / 2br - 950ft² - Beautiful apartment (kitsilano / kits point)"`.

Regex (best-effort; failures leave fields `None`):
- Price: `r"^\$?(\d{3,5})\b"` at start of title
- Bedrooms: `r"\b(\d)br\b"` → 1–9; `r"\bstudio\b"` → 0.5
- Sqft: `r"\b(\d{2,5})ft²\b"` (informational only)
- Neighborhood hint: parenthetical at end, normalized against `NEIGHBORHOOD_POSTAL_SEEDS`

### 6.5 Rate limiting & robots.txt

- `rate_limit_per_second = 1.0` (legal.md ceiling).
- Random 500–1500ms jitter before each request.
- `asyncio.Semaphore(1)` + last-request-time guard in adapter base ensures no parallel requests against the same source even under multi-neighborhood fan-out.
- robots.txt parsed at adapter init (`urllib.robotparser`), cached for process lifetime, re-checked on restart. Disallow path → `RobotsDisallowedError` → adapter `health_check()` returns `blocked`.

### 6.6 Health check

```python
async def health_check(self) -> AdapterHealth:
    # Fetch the bare RSS feed (no filters) with 5s timeout.
    # ok        if 200 + parseable + has entries
    # degraded  if 200 but empty entries OR parse warning
    # blocked   if 403 / 429 / robots.txt disallows
```

## 7. Frontend (Filter UI + Results)

### 7.1 What ships fully functional

- Bedrooms (chips: studio · 1 · 2 · 3 · 4+, multi-select → min/max)
- Price min/max (numeric inputs, validated)
- Neighborhood multi-select (the ~25 entries that map to postal seeds)
- Free-text keywords (chip input, AND-style)
- Sort dropdown: newest / price asc / price desc / bedrooms
- View switcher: Cards / List (Map / Split disabled with Phase 7 tooltip)
- Per-card actions: save · hide · contacted · open original (local-only)
- Empty / loading / error states
- Pagination: "Load more" button (`offset += limit`)

### 7.2 What ships disabled-with-hint

`<DisabledControl>` wraps each control fully laid out, greyed, with a phase badge:

- School catchment dropdown — "Phase 4 — geocoding"
- Pets radio — "Phase 3 — more sources"
- Furnished radio — "Phase 3"
- Available-after date picker — "Phase 3"
- Transit walk-time input — "Phase 4 — transit data"

Frontend reads `unsupported_filters` from `/search` response. If a future code path sets one of those, a banner appears: "Pets filter ignored — no source supports it yet."

### 7.3 Cross-platform constraints (per CLAUDE.md)

- All UI uses `View` / `Text` / `Pressable` / `ScrollView` / `FlatList`. No `<div>` / `<button>`.
- Storage: `apps/web/src/storage/listingActions.ts` exports one interface; runtime branches on `Platform.OS` to use AsyncStorage (native) or localStorage (web).
- No browser-only APIs leak in. External links via `expo-linking`.
- `<ListTable>` virtualization: `FlatList` with `getItemLayout` for fixed-height rows (works on iOS/macOS too).

### 7.4 State management

- React Context for `NormalizedQuery` + setter.
- No Redux / Zustand. Phase 2 will add a few more context fields (`nlQueryText`, `parsedChips`); still won't justify a global store.

### 7.5 Visual design

Minimum viable, honest aesthetic. No polish pass — that's Phase 7.

- Mobile (≤768px): single column; filter panel as collapsible sheet.
- Tablet (>768px): filter sidebar + results.
- Desktop (≥1024px): three-column card grid.
- Dark mode follows `useColorScheme`. Single `theme.ts` with light/dark token sets. No theme toggle UI.
- Skeleton loading states (no spinners) so layout doesn't jump.

## 8. Testing Strategy

Three layers + property-based, both backend and frontend (per user choice "C").

### 8.1 Backend unit (pytest)

| Module | Coverage |
|---|---|
| `url_builder.py` | Each filter field maps correctly; unknown neighborhoods dropped; multi-neighborhood produces N URLs; `hasPic=1` default |
| `title_parser.py` | Price/bedrooms/sqft/neighborhood extraction across ~30 sanitized real CL title strings |
| `rss_parser.py` | feedparser entry → RawListing; missing fields stay None; geo coords parsed; snippet ≤200 chars |
| `adapters/base.py` | Rate limiter ≥1s between calls; jitter 500–1500ms; robots.txt consulted; disallow → `RobotsDisallowedError` |
| `aggregator/freshness.py` | Cache key stable for equivalent queries; TTL math; `force_refresh` bypasses; canonical JSON order-independent |
| `aggregator/service.py` | Cache hit doesn't call adapter; cache miss calls + persists; adapter exception → degraded; unsupported filters stripped |
| `storage/repositories.py` | Insert/upsert/lookup; `last_seen_at` updates without changing `id`; FTS5 sync triggers fire; SchoolCatchments column ↔ object mapping |
| `http/search.py` | 422 on malformed; 200 shape matches `SearchResponse`; pagination; sort enum applied |

### 8.2 Backend integration

One test, full pipeline, recorded fixtures only:

```python
# tests/integration/test_search_end_to_end.py
async def test_search_craigslist_e2e(tmp_path):
    # 1. Real SQLite at tmp_path; alembic upgrade head
    # 2. Register CraigslistAdapter; respx stubs httpx with recorded RSS body
    # 3. POST /search with realistic NormalizedQuery via TestClient
    # 4. Assert 200, listings count > 0, cache_status="miss"
    # 5. Hit /search again same query — cache_status="fresh", no httpx calls
    # 6. force_refresh=true — httpx called again
```

`respx` stubs the `httpx.AsyncClient.get` boundary. Never hits live CL in CI.

**Recording the fixture:** `scripts/record_craigslist_fixture.py` does one live fetch in dev, redacts contact info, writes to `tests/fixtures/craigslist/`. Re-run only when CL's RSS changes.

### 8.3 Backend property-based (Hypothesis)

1. **`url_builder` invariants:** any `NormalizedQuery` → syntactically valid URL with only known param keys, no duplicates, all values URL-encoded.
2. **`title_parser` doesn't crash:** any string (incl. unicode, emoji, Korean) → `TitleParseResult` (never raises). Output values, when present, satisfy type constraints.
3. **`freshness.cache_key` stability:** `cache_key(q1) == cache_key(q2) ⇔ q1 == q2`.

### 8.4 Frontend component (Jest + jest-expo + RTL)

| Component | Coverage |
|---|---|
| `<FilterPanel>` | All controls render; values update query; supported vs disabled-with-hint render correctly |
| `<NormalizedQueryProvider>` | Both filter UI and (future) NL chips read/write same object; reset clears all |
| `<ListingCard>` | Title, price, beds, source badge, photo/placeholder; action buttons fire callbacks; "open original" opens source_url |
| `<ListingTable>` | Virtualized rows render visible window only; sort callback on header click |
| `<ResultsToolbar>` | View switcher updates parent state; sort dropdown fires callback; total shown |
| `<SearchScreen>` | Empty / loading / error / success states — one snapshot per state |

### 8.5 Frontend E2E (Playwright, web target only)

```ts
// apps/web/e2e/search.smoke.spec.ts
test('filter search end-to-end against stubbed API', async ({ page }) => {
  // 1. MSW intercepts POST /search → fixture of 5 listings
  // 2. Boot Expo web dev server
  // 3. page.goto('/'), set bedrooms_min=2, price_max=3000
  // 4. Click "Search"
  // 5. Expect 5 listing cards visible
  // 6. Switch to list view → 5 rows
  // 7. Click "save" on a card → enters saved state
});
```

Native targets (iOS / macOS) are out of scope for Phase 1 E2E — Detox lands in Phase 8.

### 8.6 CI gates

```
backend job:
  - ruff check && ruff format --check
  - mypy
  - pytest -m "not integration"      # unit + property
  - pytest -m integration            # e2e w/ recorded fixtures
  - coverage --fail-under=85

frontend job:
  - tsc --noEmit
  - eslint
  - jest --coverage (branches ≥75%, lines ≥80%)
  - playwright test                  # smoke only
```

### 8.7 Fixtures committed to repo

```
apps/api/tests/fixtures/craigslist/
  vancouver_apa.rss              # 50 entries, sanitized
  empty_feed.rss                 # 0 entries
  malformed.rss                  # parse-error case
  robots_txt_allowed.txt
  robots_txt_disallowed.txt
apps/api/tests/fixtures/titles/
  real_titles.json               # 30 sanitized titles + expected parses
apps/web/__fixtures__/
  search_response.json           # 5 listings
```

### 8.8 What is NOT tested

- Third-party libs (`feedparser`, `httpx`, `aiosqlite`, SQLAlchemy internals)
- Live Craigslist responses (never in CI)
- React Native rendering on iOS/macOS (Phase 8)
- LLM behavior (Phase 2)

## 9. Configuration

`apps/api/rentwise/settings.py`:

| Env var | Default | Purpose |
|---|---|---|
| `RENTWISE_DB_URL` | `sqlite+aiosqlite:///./data/rentwise.db` | Async SQLite path |
| `RENTWISE_SEARCH_CACHE_TTL_SECONDS` | `900` | 15-min freshness |
| `RENTWISE_SEARCH_PAGE_DEFAULT` | `50` | Default page size |
| `RENTWISE_SEARCH_PAGE_MAX` | `200` | Max page size |
| `RENTWISE_CRAIGSLIST_REGION` | `vancouver` | RSS subdomain |
| `RENTWISE_USER_AGENT` | (existing) | Identification per legal.md |

`apps/web/.env.example` adds `EXPO_PUBLIC_API_URL=http://localhost:8000`.

## 10. Definition of Done

### PR-1 (backend) merge gates
1. Backend CI green (lint, type-check, unit + property + integration, ≥85% line coverage).
2. `docker compose up api` boots cleanly; `alembic upgrade head` runs on first start; `/health` 200; `/search` returns valid `SearchResponse` for empty query.
3. Manual smoke against live Craigslist Vancouver, recorded in PR description with sample listings.
4. `docs/legal.md` per-source notes updated.
5. README source list updated (Craigslist ✅).
6. `docs/roadmap.md` Phase 1 backend chunks marked complete.

### PR-2 (frontend) merge gates
1. Frontend CI green (`tsc --noEmit`, eslint, jest with coverage, Playwright smoke).
2. Web manual run-through (empty / fetch / sort / view switch / save-hide-contacted / error) — screenshots in PR description.
3. iOS simulator manual run-through.
4. `docker compose up` (api + web together) — search end-to-end from clean DB.
5. `docs/roadmap.md` Phase 1 frontend chunks marked complete.

PR-2 is blocked on PR-1 merge.

## 11. Risks

| Risk | Mitigation |
|---|---|
| CL changes RSS schema | Recorded fixtures pin parsing assumptions; live-fetch smoke is canary |
| CL blocks our IP / rate-limits | Adapter sets `source_health="blocked"`, returns 200 + warning banner |
| legal.md drift | PR-1 gate explicitly requires updating per-source notes |
| Listings dataset growth | SQLite handles 50k easily; LRU sweeper in Phase 5 |
| Test flakiness from real timestamps | Injectable `Clock` protocol; tests use frozen clock |

## 12. Phase 5+ Seams Documented in Code

- `aggregator/service.py` — comment marking the spot APScheduler will hook into for saved-search refresh.
- `searches.is_saved` column — currently always 0; Phase 5 flips it.
- `apps/web/src/storage/listingActions.ts` — single-interface abstraction so server-side persistence is a swap.

## 13. Decisions Captured (from brainstorm)

| Decision | Choice |
|---|---|
| Issue split | C: backend issue + frontend issue, by layer |
| Test depth | C: unit + integration + Playwright smoke + Hypothesis property tests |
| Filter coverage strategy | B: full UI ships, adapter capabilities declare what works, unsupported surfaces in API + UI |
| Ingestion model | C scoped to A for Phase 1: pull-on-demand with cache freshness; scheduler deferred to Phase 5 |
| School catchment shape | Three nullable indexable columns (elementary / middle / secondary); Pydantic `SchoolCatchments` object |
