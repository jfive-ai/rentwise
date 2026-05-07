# Phase 3 — Launcher + Browser Extension Capture: Design Spec

**Date:** 2026-05-07
**Scope:** Phase 3 of `docs/roadmap.md` after the user-driven pivot. Adds multi-source capture via a browser extension paired with a launcher in the RentWise web app. Covers the five originally TOS-blocked sources (Rentals.ca, PadMapper, Zumper, REW.ca, liv.rent) and Facebook Marketplace.
**Out of scope:** Server-side scraping of any source covered here (TOS-blocked); cross-source dedup (Phase 4); saved searches and alerts (Phase 5); map view (Phase 7); native mobile builds (Phase 8); automatic login or any session/credential handling.

## 1. Goals & Non-Goals

### Goals
- Enable RentWise to surface listings from the five TOS-blocked sources + Facebook Marketplace **without** any server-side fetch of those sites.
- One user click launches a search across all enabled sources; each source opens in a tab in the user's own browser; the extension extracts listings already rendered on those pages.
- Reuse the existing `RawListing` / `NormalizedListing` data model, the SQLite + Alembic storage, and the Phase 1 search/results UI. Captured listings appear alongside Craigslist results in the same `/search` response.
- Establish a clean legal posture: every fetch is initiated by a user gesture in the user's own browser session; document the rationale in `docs/legal.md`.
- Provide a per-source enable toggle, a visible "captured" indicator, and per-source breakage handling so a source whose DOM changes does not silently lose data.

### Non-Goals
- **No background fetch.** The extension never `fetch()`s a listing or search URL on its own. It reacts only to pages the user (or the launcher click) caused the browser to load.
- **No autonomous navigation.** The extension does not click links, paginate, scroll, or open further tabs on its own. If the user wants page 2 of a search, the user clicks page 2.
- **No login automation.** The extension never authenticates to any source on the user's behalf, never reads cookies/tokens for any source, never stores per-source credentials.
- **No cross-source dedup in Phase 3.** Capturing the same listing from two sources produces two records; merging is Phase 4.
- **No browsers other than Chromium-based at first ship.** Firefox MV3 is best-effort; Safari Web Extensions are out of scope.

## 2. PR Sequencing

Three PRs against `main`. Each must merge before the next.

1. **PR-A — Backend `/capture` endpoint** (`feat/phase-3-capture-api`)
   Adds the local capture endpoint, shared-secret auth, schema models, repository upsert by `(source, source_listing_id)`, capture-method tracking. Test-only — no extension yet.
2. **PR-B — Extension scaffold + first two sites** (`feat/phase-3-extension-scaffold`)
   Manifest, background service worker, popup, options, capture client, content scripts for **Rentals.ca and PadMapper** (chosen first: most uniform DOM, well-documented public URL patterns). Build pipeline + jsdom unit tests.
3. **PR-C — Launcher in web app + remaining four sites** (`feat/phase-3-launcher`)
   `LauncherButton` in the filter panel; per-source URL builders; "Run search across sources" flow; content scripts for **Zumper, REW.ca, liv.rent, Facebook Marketplace**.

GitHub tracking issues mirror this split. Each later PR depends on the previous being merged so `main` is always green.

## 3. Architecture

### 3.1 Component overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                             User's browser                                │
│                                                                           │
│  ┌─────────────────────────┐   click "Search across sources"             │
│  │ RentWise web app (Expo) │ ──────────────────────────────┐             │
│  │   FilterPanel +         │                                ▼             │
│  │   LauncherButton        │   window.open(url) per enabled source        │
│  └─────────────────────────┘                                              │
│           │                                                               │
│           │ /search                                                       │
│           ▼                                                               │
│  ┌────────────────────────────────────────────┐    ┌──────────────────┐ │
│  │              tab: rentals.ca                │    │   tab: zumper    │ │
│  │  ┌──────────────────────────────────────┐  │    │ (same pattern)   │ │
│  │  │ Extension content script (rentals_ca)│  │    │                  │ │
│  │  │   reads DOM → CapturePayload         │  │    │                  │ │
│  │  └──────────────────────────────────────┘  │    │                  │ │
│  └────────────────────┬───────────────────────┘    └──────────────────┘ │
│                       │ chrome.runtime.sendMessage                        │
│                       ▼                                                   │
│  ┌────────────────────────────────────────────┐                          │
│  │ Extension background service worker        │                          │
│  │   POST http://127.0.0.1:8000/capture        │                          │
│  │   X-RentWise-Token: <shared-secret>         │                          │
│  └────────────────────┬───────────────────────┘                          │
└───────────────────────┼───────────────────────────────────────────────────┘
                        │ localhost only
                        ▼
                ┌───────────────────────┐
                │   FastAPI: /capture   │
                │   verify token        │
                │   upsert listing      │
                │   write source_health │
                └───────────────────────┘
```

### 3.2 Module layout (new + extended)

```
apps/api/rentwise/
  capture/
    __init__.py
    router.py                     # POST /capture
    auth.py                       # shared-secret header verification + constant-time compare
    schemas.py                    # CapturePayload, CaptureResponse Pydantic models
    pairing.py                    # GET /capture/pair → generates and persists the shared secret
  storage/
    repositories.py               # extended: ListingRepo.upsert_by_source_url(...)
                                  #           SourceHealthRepo.record_capture(...)
  models.py                       # extended: capture_method enum on NormalizedListing
  alembic/
    versions/
      0003_capture_method.py      # add capture_method column + capture_pairing table

apps/extension/                   # new top-level project
  manifest.json                   # MV3, host_permissions limited to source origins
  package.json
  tsconfig.json
  vite.config.ts                  # MV3 bundling (vite-plugin-web-extension)
  src/
    background/
      service-worker.ts           # message router; POSTs to /capture
    content/
      base.ts                     # parsing helpers, throttle, idempotency cache
      capture-client.ts           # send-to-background helper
      sites/
        rentals_ca.ts
        padmapper.ts
        zumper.ts
        rew_ca.ts
        liv_rent.ts
        facebook_marketplace.ts
    popup/
      Popup.tsx                   # status, per-site toggles, "captured today" count
    options/
      Options.tsx                 # paste shared secret, choose RentWise API URL
    schemas/
      capture.ts                  # zod schema mirroring backend Pydantic
    storage.ts                    # chrome.storage.local wrapper
  tests/
    fixtures/                     # saved HTML snapshots per site
      rentals_ca/
        search_results.html
        listing_detail.html
      padmapper/...
    sites/
      rentals_ca.test.ts          # jsdom + content script under test

apps/web/
  src/
    launcher/
      LauncherButton.tsx          # mounts in FilterPanel; calls buildSearchUrls + window.open
      buildSearchUrls.ts          # NormalizedQuery → per-source URL[]
      sources.ts                  # source registry: { id, name, enabled, urlBuilder }
      ExtensionStatus.tsx         # shows pairing state + reachable check
    settings/
      ExtensionPairing.tsx        # generates shared secret, displays paste-into-extension flow
```

### 3.3 Data flow (single launcher click)

1. User configures filters (or NL query) in the existing Phase 1 UI.
2. User clicks **"Search across sources"**.
3. `buildSearchUrls(NormalizedQuery)` produces one URL per enabled source. Sources for which no URL can be built (the query exceeds the source's URL-expressible filters) are listed in a small "would not include" affordance and skipped.
4. The web app calls `window.open(url, '_blank')` for each URL, in sequence with a small delay (350ms) to avoid the popup blocker. Source order is fixed for deterministic UX.
5. Each opened tab loads in the user's browser session. The page renders normally — the user can interact with it.
6. The extension's content script for that origin runs at `document_idle`. It checks the URL against per-site path patterns (search-results vs listing-detail vs neither) and reads the DOM accordingly.
7. Extracted records go to the background service worker via `chrome.runtime.sendMessage`.
8. The service worker sends `POST http://127.0.0.1:8000/capture` with the shared-secret header. The host is configurable via the options page for users who run the API on a different port.
9. `/capture` verifies the secret, upserts each listing into SQLite (`ListingRepo.upsert_by_source_url`), updates `source_health`, and returns counts.
10. The RentWise web app's results view either polls `/search` on a short timer while the launcher session is active, or — if you keep one open — re-runs the same query and shows the new captured rows alongside Craigslist's. Polling is the v1 choice (simple, no SSE infra). SSE/websocket is a Phase 5 candidate.

## 4. Per-site URL builders

Each source registers a builder that takes a `NormalizedQuery` and returns either a search URL or `null` (if the query cannot be expressed in the source's URL params). The builder is the **only thing** the extension and web app need to know about a source's search interface — every other piece of the source's identity lives in the content script.

| Source | Search URL pattern | Notes on URL-expressible filters |
|---|---|---|
| Rentals.ca | `https://rentals.ca/vancouver?...` | bedrooms, bathrooms, price min/max, pets, neighborhood as `?neighborhood=` slug |
| PadMapper | `https://www.padmapper.com/apartments/vancouver-bc?...` | bedrooms, price, beds, neighborhood by bbox |
| Zumper | `https://www.zumper.com/apartments-for-rent/vancouver-bc?...` | bedrooms, price; neighborhood as path segment |
| REW.ca | `https://www.rew.ca/properties/areas/vancouver-bc/type/rent?...` | bedrooms, price; broader filters via search-form params |
| liv.rent | `https://liv.rent/listings/vancouver?...` | bedrooms, price; pets; in-suite amenities |
| Facebook Marketplace | `https://www.facebook.com/marketplace/vancouver/propertyrentals?...` | very limited; price min/max + bedrooms only |

Filters that cannot round-trip through a source's URL fall back to "open the search page; the user will refine on the site." The launcher flags this with a small "Rentals.ca won't filter on pet-friendly — refine on the page" line under the source card.

The exact URL parameter names are **not** in this spec — they are read from each site's public search form during PR-B/PR-C and committed alongside the content script. Sites change these; selectors and URL-param names are versioned together.

## 5. Content scripts

### 5.1 Activation gating

Each content script is registered in the manifest with a `matches` glob restricted to the source's listing-related paths (e.g. `https://rentals.ca/vancouver*`, `https://rentals.ca/vancouver/*` for detail pages). It also self-checks the URL against finer patterns inside `document_idle` to decide search-vs-detail mode.

The script does **nothing** outside those URL patterns. There is no global content script.

### 5.2 Extraction strategy

Per page type:

- **Search results pages** — extract every visible listing card on the rendered page. Capture only fields that are present on the card (URL, title, price, beds, neighborhood, thumbnail URL, listing ID parsed from URL). Snippets and full descriptions are **only** captured on detail pages, never from card text.
- **Listing detail pages** — extract the full per-listing fields: URL, title, price, beds, baths, sqft, neighborhood, posted date, photo URLs (URLs only, never bytes), description (truncated to 200 chars per `docs/legal.md`).

Card-level vs detail-level captures upsert into the same row keyed on `(source, source_listing_id)`. Whichever capture has more fields wins; missing fields are not overwritten with nulls.

### 5.3 Selector strategy

Every site uses a versioned selector schema:

```ts
// apps/extension/src/content/sites/rentals_ca.ts
export const SCHEMA_VERSION = "2026-05-07";

export const SELECTORS = {
  searchResultsCard: "...",
  listingDetailContainer: "...",
  // ...
};
```

If a required selector returns no nodes, the script:
1. Logs to extension console with the schema version.
2. Sends a `source_health=degraded` ping to `/capture/health` (no listings, just the failure).
3. Shows a small toast in the extension popup: "Rentals.ca capture is broken. Update the extension."

This is the difference between silent loss and visible degradation.

### 5.4 Idempotency on the page

A content script may run multiple times for one page (SPA navigations, infinite scroll DOM mutations). It maintains an in-memory `Set<source_listing_id>` for the lifetime of the tab and skips IDs already sent. Server-side `upsert` makes this best-effort; the in-memory cache keeps traffic clean.

### 5.5 What is **never** captured

Per `docs/legal.md`:

- ❌ Photo bytes (URLs only)
- ❌ Verbatim listing descriptions in full (≤200-char snippet only)
- ❌ Landlord contact details beyond a link back
- ❌ Any data behind a login wall
- ❌ Any per-user PII

If the user is logged into a source, the extension does not capture more than it would for an anonymous visitor. Specifically, it does not read user accounts, saved searches, or messages.

## 6. Local capture API contract

### 6.1 Auth — shared-secret header

The extension and the API share a 32-byte random secret stored in:
- Server-side: a single row in a new `capture_pairing` table.
- Extension-side: `chrome.storage.local` under key `rentwise.captureToken`.

Pairing flow:
1. User opens RentWise → Settings → Extension.
2. Web app calls `GET /capture/pair`. Server generates a fresh secret if none exists, returns `{ token, server_url }`. (If a secret already exists, the server returns it — the user can rotate via a "Rotate token" button, which deletes and regenerates.)
3. The web app shows the token + server URL in a copy-paste card. The user opens the extension's options page and pastes both.
4. Extension stores both values in `chrome.storage.local`.
5. Subsequent capture requests include the token in `X-RentWise-Token`.

Server-side comparison uses `hmac.compare_digest` (constant-time). Missing or wrong tokens return 401.

The server binds to `127.0.0.1` by default (already true in the existing FastAPI setup). The token + localhost binding together is what keeps random web pages from POSTing to your local API.

### 6.2 Endpoints

```
POST /capture
  Headers:
    X-RentWise-Token: <shared secret>
    Content-Type: application/json
  Body:
    {
      "source": "rentals_ca" | "padmapper" | "zumper" | "rew_ca"
              | "liv_rent" | "facebook_marketplace",
      "captured_at": <ISO8601>,
      "page_type": "search_results" | "listing_detail",
      "page_url": <string>,                 // the URL the user is actually viewing
      "schema_version": <string>,           // matches the content script's SCHEMA_VERSION
      "listings": [ <CaptureListing>, ... ] // empty array allowed (e.g. "page seen, no listings")
    }
  200 Response:
    {
      "accepted": <int>,
      "skipped_duplicates": <int>,
      "errors": [ { "index": <int>, "message": <string> }, ... ]
    }

POST /capture/health
  Headers: X-RentWise-Token
  Body: { "source": <id>, "schema_version": <string>, "status": "degraded", "reason": <string> }
  Response: 204

GET /capture/pair                          # web-app facing, no token required, gated by Origin
  200: { "token": <string>, "server_url": "http://127.0.0.1:8000" }

POST /capture/pair/rotate                  # web-app facing, gated by Origin
  204
```

### 6.3 `CaptureListing` schema

Mirrors the existing `RawListing` Pydantic model with two additions:

```python
class CaptureListing(BaseModel):
    source_listing_id: str               # parsed from URL by the content script
    url: HttpUrl
    title: str | None = None
    price: int | None = None
    bedrooms: float | None = None        # 0 = studio, 0.5 = den, etc.
    bathrooms: float | None = None
    sqft: int | None = None
    neighborhood: str | None = None
    posted_at: datetime | None = None
    thumbnail_url: HttpUrl | None = None
    photo_urls: list[HttpUrl] = []
    description_snippet: str | None = Field(default=None, max_length=200)

    capture_method: Literal["extension"] = "extension"
    page_type: Literal["search_results", "listing_detail"]
```

Snippet length is enforced at the schema, not just trusted from the client.

### 6.4 Upsert semantics

`ListingRepo.upsert_by_source_url(source, source_listing_id, fields, capture_method, captured_at)`:

- Match on `(source, source_listing_id)`.
- New row → insert with `first_seen_at = captured_at`, `last_seen_at = captured_at`.
- Existing row → update only fields where the new value is non-null; advance `last_seen_at`; do **not** overwrite an existing non-null value with a null.
- Never overwrites a `listing_detail`-level field from a `search_results` capture (detail wins).
- Records `capture_method` so cross-source dedup in Phase 4 can distinguish extension-sourced from server-sourced rows.

## 7. Storage model extensions

Migration `0003_capture_method.py`:

```sql
ALTER TABLE listings ADD COLUMN capture_method TEXT
    CHECK (capture_method IN ('server', 'extension'))
    NOT NULL DEFAULT 'server';

ALTER TABLE listings ADD COLUMN first_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE listings ADD COLUMN last_seen_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP;

CREATE TABLE capture_pairing (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    token TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    rotated_at DATETIME
);
```

The `id = 1` constraint enforces a singleton row.

## 8. UX requirements

### 8.1 Web-app launcher

- Mount: `LauncherButton` lives in the existing `FilterPanel`, beneath the existing "Search Craigslist" button (which keeps working unchanged).
- States:
  - **Default:** "Search across sources (5 sites)" — count reflects number of enabled sources.
  - **Pending pairing:** disabled with a small "Pair the extension first →" link to settings.
  - **Some sources can't express this query:** secondary line "PadMapper won't filter on pet-friendly — refine on the page after it opens."
- On click: opens N tabs in sequence (350ms apart). The current RentWise tab stays focused. A small toast appears: "Opened N tabs. Captured listings will appear here within seconds."
- Results list re-polls `/search` every 2s for 30s after the click, then stops.

### 8.2 Extension popup

- Header: pairing status (✅ paired / ⚠️ not paired) + "captured today" count.
- Per-source list with:
  - Toggle (enable/disable capture)
  - Last-capture timestamp + count
  - Schema version
  - "⚠️ Selectors broken" badge if `source_health=degraded`
- Footer: "Open RentWise" button.

### 8.3 In-page indicator

When a content script captures a page, it briefly shows a small bottom-right banner:

> ✓ RentWise captured 12 listings on this page

The banner auto-hides after 3s. It does not block any source-site UI. The user can disable the banner per-source in the popup.

## 9. Legal posture rationale

Per the Phase 3 pivot in `docs/roadmap.md` and the per-source TOS findings in `docs/legal.md`, the design above is structured to keep RentWise out of the "automated software / bot / spider" category in those clauses:

1. **Each fetch is initiated by a user gesture.** The `window.open` calls happen synchronously inside the user's click handler. No tab is opened by the extension or by RentWise outside that gesture.
2. **Each fetch happens in the user's own browser session.** The user-agent is the user's browser. Cookies, session, and authentication state are the user's, used exactly as if the user typed the URL.
3. **The extension never originates a network request to a source's domain.** It reads the rendered DOM only. Network traffic to source domains comes from the browser, in response to user navigation.
4. **The extension does not navigate, click, scroll, or paginate on its own.** It is a passive reader.
5. **Captured data is stored only on the user's machine** (localhost SQLite), never re-published, and only ≤200-char snippets of any descriptive text per `docs/legal.md`.

This is not a guarantee of legal safety — it is a documented best-effort posture. As `docs/legal.md` says, this is not legal advice; before any non-personal use, get a lawyer.

What we **deliberately do not do**, even though it would be more convenient:
- Background-fetch source pages from the extension (would re-introduce "automated" status).
- Auto-paginate or auto-scroll on source pages (would re-introduce "automation" status).
- Build a hosted version of RentWise where the same extension reports back to a shared server (would change the "user's local PC" framing).

## 10. Security & privacy

- **Localhost-only API.** FastAPI binds to `127.0.0.1`; CORS is restricted to `http://localhost:*` and `http://127.0.0.1:*`. The capture endpoint additionally requires the shared-secret header.
- **No third-party callbacks.** The extension never sends data anywhere except the user's local API.
- **Token rotation.** User can rotate the pairing token at any time; the old token immediately stops working.
- **No source credentials.** Extension never reads, stores, or transmits cookies/tokens for any source. Source sessions stay in the browser where they belong.
- **Telemetry: none.** No analytics, no error reporting beyond the local extension console.
- **Clear data flow.** Settings page exposes "Show captured data" + "Delete all captured data." The latter purges `listings` rows where `capture_method = 'extension'` and any associated FTS rows.

## 11. Test plan

### 11.1 Unit (extension)

- Per-site content scripts run against committed HTML fixtures using jsdom.
- Each fixture is a real `view-source:` snapshot saved by hand (not fetched by automation).
- Tests assert: extracted field values are correct; missing-selector cases produce a single `degraded` ping; idempotency cache prevents duplicate sends.

### 11.2 Unit (backend)

- `/capture` endpoint: token verification, schema validation, snippet length enforcement, upsert merging behavior (detail wins over search-results), `last_seen_at` advancement.
- `/capture/pair`: singleton enforcement, rotation deletes-then-creates, returned URL matches `settings.api_base_url`.
- `ListingRepo.upsert_by_source_url`: null-skip behavior, capture-method preservation.

### 11.3 Integration

- **Backend:** end-to-end against an in-memory SQLite — POST a synthetic capture batch, run `/search`, assert rows appear with `capture_method=extension`.
- **Extension:** Playwright launches Chromium with the unpacked extension loaded; opens each fixture HTML served from a local static server; asserts the extension posts to a stub capture endpoint.

### 11.4 Live / smoke

- A manually-runnable script (`pytest -m live`, gated by `RUN_LIVE_EXTENSION_TESTS=1`) pairs a real extension build against a real RentWise dev API and exercises one search per source. Not run in CI. Fixture refresh signal — when this fails, the fixtures need updating.

### 11.5 Selector-rot detection

- Every two weeks, a maintenance script diffs the live source pages against the saved fixtures and fails if the structural shape changed. This is run locally, not in CI, and not against any source's terms-prohibited bulk-fetch pattern — it loads one page per source manually via the maintainer.

## 12. Open questions

- **Popup blocker behavior.** Most modern Chrome blocks 2nd+ tab from a single click event. The 350ms-spaced sequential opens may still trigger the blocker. Mitigation: detect `window.open` returning `null`, surface "Allow popups for RentWise" hint inline. **Decision needed before PR-C.**
- **Pagination.** v1 captures only the visible first page of search results. Should the launcher also open page 2 / page 3? Probably not in v1 (too aggressive); revisit if users find v1 thin.
- **Distribution.** Chrome Web Store requires a developer account + review. Sideload via `chrome://extensions` is fine for MVP but breaks for non-technical users. Plan to start sideloaded and reassess if sharing.
- **Firefox.** Firefox MV3 supports most of what we use. We'll commit to Firefox parity only if it's cheap; otherwise document Chrome-only.
- **liv.rent partnership.** If the parallel partnership track in `docs/roadmap.md` succeeds, liv.rent moves out of the extension and into a server-side adapter. The launcher's source registry is structured so this is a one-line swap.
- **Polling vs SSE.** v1 polls `/search` every 2s for 30s after a launcher click. Phase 5 may revisit this with SSE for live-update-on-capture across all open RentWise tabs.

## 13. Risks & mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Source DOM changes break a content script | Captured rows go missing for that source | Versioned selector schema + `degraded` ping + popup badge; selector-rot detection job |
| Popup blocker prevents multi-tab open | Launcher is silently broken | Detect null `window.open`; show inline "allow popups" hint; degrade to one-source-per-click flow |
| User pastes the wrong API URL | Capture silently fails | Pairing flow validates with a `GET /capture/pair/echo` round-trip before saving |
| Token leak via misconfigured API | Random pages POST captures | Localhost binding + token + Origin checks on `/capture/pair`; rotate-token affordance |
| User logs into a source, expects RentWise to capture private data | Privacy violation | Content scripts never read login-gated pages; popup notes "captures public listing data only" |
| Source treats extension traffic as bot-like even when user-driven | IP block / CAPTCHA on the source site | Per-source disable toggle so the user can opt out without uninstalling the whole extension |

## 14. What lands in each PR (summary)

**PR-A — Backend `/capture` endpoint:**
- `apps/api/rentwise/capture/{router,auth,schemas,pairing}.py`
- `ListingRepo.upsert_by_source_url`, capture-method column, capture_pairing table
- Migration `0003_capture_method.py`
- Tests: token auth, upsert merge semantics, pair rotation
- No web-app or extension changes

**PR-B — Extension scaffold + Rentals.ca + PadMapper:**
- `apps/extension/` MV3 project, build pipeline, popup, options
- `background/service-worker.ts`, `content/{base,capture-client}.ts`
- `content/sites/{rentals_ca,padmapper}.ts` + jsdom unit tests
- HTML fixtures committed
- README explaining sideload steps

**PR-C — Launcher + remaining four sites:**
- `apps/web/src/launcher/{LauncherButton,buildSearchUrls,sources}.tsx`
- Extension content scripts for `zumper`, `rew_ca`, `liv_rent`, `facebook_marketplace`
- Settings → Extension pairing UI
- Polling logic on the results screen
- Phase 3 milestone tickable: search across 6 sources from one query
