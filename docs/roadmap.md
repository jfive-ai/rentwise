# Roadmap

## Phase 0: Foundations (Week 1-2)
**Goal:** Repo set up, can run a local dev environment.

- [x] Project naming, README, docs
- [ ] GitHub repo with issue templates and PR template
- [ ] License (MIT) and CONTRIBUTING.md
- [ ] Backend skeleton: FastAPI app that runs and returns hello world
- [ ] Frontend skeleton: Expo app with placeholder search screen
- [ ] Docker Compose dev setup
- [ ] CI: GitHub Actions for lint + tests

## Phase 1: First Adapter — Craigslist (Week 3)
**Goal:** Prove the end-to-end flow with the easiest, most TOS-friendly source.
**Why Craigslist first?** Has RSS feeds, no HTML scraping needed, easiest source to ship cleanly.

- [x] Define `SourceAdapter` Protocol
- [x] Implement `CraigslistAdapter` using the RSS feed
- [x] Define `RawListing`, `NormalizedListing`, and `NormalizedQuery` data models
- [x] SQLite schema + migrations (Alembic)
- [x] Aggregator that calls one adapter
- [x] **Frontend: filter-based search UI** (faceted controls, no NL yet)
- [x] **Frontend: results display with two views — card grid (default) + list/table**
- [x] **Frontend: per-card actions — save / hide / contacted / open original**
- [x] **Frontend: sort controls (newest, price asc/desc, bedrooms)**
- [x] **Milestone:** Search Craigslist Vancouver with structured filters, switch between card/list views

## Phase 2: Natural Language Layer (Week 4)
**Goal:** Add NL search **on top of** the existing filter UI — bilingual (English + Korean) from day 1. Both modes coexist; users can switch at will.

- [x] LiteLLM integration with provider-agnostic config
- [x] First-run setup wizard (LLM provider + API key)
- [x] Settings UI for switching LLM at runtime
- [x] Tool-use schema for query translation (works across Anthropic/OpenAI/Google/OpenRouter)
- [x] Bilingual system prompt (Korean + English) with Vancouver-specific neighborhoods, schools, SkyTrain
- [x] **Frontend: NL search bar above the filter UI** + parsed-query preview with editable chips
- [x] **Frontend: mode toggle** — "Natural language" ⇄ "Filters" — sharing the same NormalizedQuery state
- [x] **Frontend: graceful fallback** — if LLM fails, show filter UI with friendly message
- [x] Test against free OpenRouter models (Qwen 2.5, Llama 3.3) for both languages
- [x] **Milestone:** "Find me a 2 bedroom in East Van under $2500" works
- [x] **Milestone:** "이스트 밴 2베드 2500불 이하" works equally well
- [x] **Milestone:** Switching from NL to filter view preserves the parsed query

## Phase 3: User-driven multi-source capture (browser extension) (Week 5-7)

**Goal:** Surface listings from Rentals.ca, PadMapper, Zumper, REW.ca, liv.rent, and Facebook Marketplace via a browser extension that captures data only from pages the user already visited in their own browser session. No server-side scraping.

**Pivot rationale:** All five originally planned server-side sources actively block bots and explicitly prohibit automated extraction in their TOS. The user-driven extension reads pages the user already loaded in their own browser, which sidesteps both the technical anti-bot defenses and the automation-targeted TOS clauses. It's identical in shape to what was originally Phase 6 (Facebook Marketplace), so Phase 6 was folded into Phase 3.

> **Note (Phase 8 pivot):** the extension turned out to be inconvenient for daily personal use. Phase 8 retires it in favor of direct adapters that run inside the macOS app. See Phase 8 below for the new plan.

### Server-side base (kept, reusable when a future source clears TOS)

- [x] Playwright adapter base class
- [x] `robots.txt` parser & cache (shipped in Phase 1, reused by Playwright base)
- [x] Rate limiter (token bucket per source) (shipped in Phase 1, reused by Playwright base)

### Originally planned server-side adapters — all TOS-blocked

  1. [~] ~~Rentals.ca~~ — TOS § 3.16 prohibits automated extraction
  2. [~] ~~PadMapper~~ — TOS § 8.4 prohibits scraping
  3. [~] ~~Zumper~~ — TOS § 11 prohibits crawl/scrape/spider (PadMapper parent; identical clause)
  4. [~] ~~REW.ca~~ — TOS forbids robot/spider access and "screen scraping" / "database scraping" by name
  5. [~] ~~liv.rent~~ — TOS § 7.1(v)/(w) prohibits scraping/indexing/data-mining and bot use

### User-driven extension (new direction)

- [x] Phase 3 design doc: extension architecture + per-site capture UX + local capture API contract
- [x] Browser extension scaffold (Chrome MV3; Firefox where the same MV3 manifest works)
- [x] Content scripts that activate **only** on listing pages the user navigated to themselves (no background fetch of pages the user did not request) — Rentals.ca + PadMapper shipped in PR-B; remaining four sites in PR-C
- [x] Local capture endpoint on the FastAPI backend with shared-secret auth bound to localhost
- [x] Per-site capture for the five blocked sources + Facebook Marketplace (was Phase 6)
- [x] Extension UI: "Save to RentWise" affordance with a clear "captured" toast; per-site enable toggle; clear off-state so the extension is dormant outside listing pages
- [x] Document the rate-limit / scraping rules in `docs/operational-rules.md` — captured pages must be ones the user requested
- [x] Launcher in the web app — one click opens N tabs in the user's browser; results re-poll for 30s
- [x] **Milestone:** User browses any of the six sources normally; matching listings appear in RentWise

### Parallel track (cancelled)

- [~] ~~Reach out to liv.rent (Vancouver-based) about an explicitly-authorized integration.~~ Cancelled by decision: the user-driven extension already covers liv.rent under the same TOS posture as the other five sources, so the partnership outreach was deprioritized. Recorded here for audit, not as planned work.

## Phase 4: Deduplication & Enrichment (Week 7)
**Goal:** Useful, clean results.

- [x] Address normalization (`pyap`; upgrade to `libpostal` when we go multi-city) — PR-A
- [x] Geocoding (Nominatim) + persistent geocode cache — PR-A
- [x] Photo perceptual hashing (`imagehash`) — PR-C
- [x] Dedup matching algorithm + confidence scoring — PR-C
- [x] School catchment lookup (VSB GeoJSON; `shapely` point-in-polygon) — PR-B
- [x] Transit lookup (TransLink slim stops; haversine + 5 km/h) — PR-B
- [x] Filters: `school_catchment` + `transit_max_walk_minutes` wired through `/search` — PR-B
- [x] UI polish: school chip, transit input, "Also on N sources" cluster affordance — PR-D
- [x] **Milestone:** "2br in Lord Byng catchment" works correctly

## Phase 5: Saved Searches & Alerts (Week 8)
**Goal:** Stop refreshing; let RentWise notify you.

- [x] Save search UI (CRUD: drawer, save form, label + alert metadata) — PR-A
- [x] Background job runner (APScheduler) — PR-B
- [x] Email notifier (SMTP) — PR-B
- [x] Web push notifications — PR-C
- [x] Alert dedup (don't notify twice for same listing) — PR-B
- [x] **Milestone:** Get an email when a new matching listing appears — PR-B

## Phase 6: ~~Facebook Marketplace via Browser Extension~~ — folded into Phase 3

Originally a standalone phase. As of the Phase 3 pivot to user-driven capture, Facebook Marketplace is one of the per-site captures handled by the same extension architecture. See Phase 3.

## Phase 7: Map View, Split View & Mobile Polish (Week 11)
**Goal:** Add map and split views; make mobile experience excellent.

- [x] Map view with MapLibre GL JS + OpenStreetMap tiles — PR-A
- [x] Marker clustering (`supercluster`) — PR-A
- [x] "Search this area" affordance after pan/zoom — PR-A
- [x] School catchment polygon overlay (toggleable) — PR-B
- [x] SkyTrain station radii overlay (toggleable) — PR-B
- [x] Split view (map + list, synced hover/selection state) — PR-B
- [x] Responsive design pass — list view default on mobile, split view default on wide desktop — PR-C-1
- [x] Filter persistence (URL params) so searches are shareable/bookmarkable — PR-C-2
- [x] PWA install support (manifest + app-shell service worker) — PR-C-3
- [x] **Milestone:** Beautiful experience on iPhone Safari and large desktop alike

## Phase 8: Personal macOS app — retire the extension, ship direct adapters

**Goal:** RentWise becomes a single packaged macOS app that does NL search → aggregate → list with one-click jump to source. The browser extension capture path is retired because it was inconvenient in daily personal use.

**Pivot rationale.** Phase 3's extension was the right call when the project was framed as "potentially shareable with others later." For a tool *I personally* use to find an apartment, asking myself to keep a browser extension installed and visit each site to "trigger" capture is friction I won't pay. The new shape: I type a query in the macOS app, it returns listings from every source I'm willing to scrape directly (within `docs/operational-rules.md` constraints — robots.txt, rate limits, no anti-bot evasion), and each result links straight to the original posting.

**Scope.**

- [x] PR-A — Package the existing Expo Universal app as a macOS app. Mac Catalyst via `expo run:ios --device "Mac"` produced an iOS-platform `.app` Finder refused to launch; we shipped an Electron shell at `apps/desktop/` instead. Build with `./scripts/build-mac.sh` (or `./scripts/build-mac.sh --install` to drop into `/Applications`). 100% of the TS source is the Expo web bundle — no native fork.
- [x] PR-B — Extension removal. Deleted `apps/extension/`, the capture router/pairing/auth modules under `apps/api/rentwise/capture/`, the launcher subsystem in the web app, and the `captures` table (Alembic `0010_drop_capture`). README source table + docs updated.
- [x] PR-C — Direct adapter: Rentals.ca. Server-side scaffold gated behind `RENTWISE_RENTALSCA_ENABLED`; honors robots.txt + the explicit query-param allow-list in the URL builder. Selectors calibrated against the synthetic test fixture only — `_extract` returns `[]` and logs `rentalsca.selectors_not_yet_calibrated` when no cards match. Re-calibration against live markup is a follow-up.
- [x] PR-D — Direct adapter: PadMapper. Same shape as PR-C; gated behind `RENTWISE_PADMAPPER_ENABLED`. Enforces in-process guards against the documented Disallow paths and the `box=` query parameter (Python's `urllib.robotparser` does not parse `Disallow: /*box=*` reliably).
- [x] PR-E — Direct adapters: Zumper + REW.ca + liv.rent — one bundled PR. All three are scaffolds with stub `_extract` returning `[]`, gated behind `RENTWISE_ZUMPER_ENABLED` / `RENTWISE_REW_ENABLED` / `RENTWISE_LIVRENT_ENABLED`. Real selectors land in follow-up PRs; do not claim coverage until then.
- [x] PR-F — Facebook Marketplace confirmed out of scope (login-walled; never automate logins). README source table marks it as such.
- [ ] **Milestone:** I can `open RentWise.app`, type "2br Kitsilano under $3000 pet-friendly", and see real results from all five direct sources within 10 seconds. *(Blocked on real selector calibration for PR-C/D/E — the `.app` ships and aggregates Craigslist today.)*

## Phase 9: Multi-user Hosted (Future)
**Goal:** Let others sign up and use it without self-hosting.

- [ ] Authentication (Auth.js / Clerk)
- [ ] Per-user encrypted credentials
- [ ] PostgreSQL + Meilisearch
- [ ] Per-user rate limit budgets
- [ ] Restore the per-source TOS verdict ledger (the old `docs/legal.md` — recoverable from git history before the Phase 8 pivot commit); a multi-user hosted version needs that scaffolding back, plus per-platform written authorization or official APIs.
- [ ] Reach out to platforms re: terms.

## Open Questions

- ~~Should we build a "user-driven" mode where the user opens their own browser and RentWise observes their activity? (More like a Pinboard for rentals than a scraper.)~~ Resolved Phase 3 — that's exactly what the extension does. Subsequently revisited in Phase 8: extension was inconvenient in daily use, so Phase 8 replaces it with direct adapters inside the macOS app.
- ~~Should we partner with one of the platforms (e.g. liv.rent is Vancouver-based and might be open to an integration)?~~ Cancelled — see the cancelled parallel track in Phase 3.
- Do we want to support the Vancouver short-term rental registry data?
