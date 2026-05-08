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
**Why Craigslist first?** Has RSS feeds, no scraping needed, lowest legal risk.

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

**Pivot rationale:** All five originally planned server-side sources have been TOS-verified and all five prohibit automated extraction (see `docs/legal.md`). The TOS prohibitions describe what RentWise's automation may not do; they do not necessarily reach activity initiated by the user in their own browser. The user-driven model is the only TOS-compliant path. It is also identical in shape to what was originally Phase 6 (Facebook Marketplace), so Phase 6 is folded into Phase 3.

### Server-side base (kept, reusable when a future source clears TOS)

- [x] Playwright adapter base class
- [x] `robots.txt` parser & cache (shipped in Phase 1, reused by Playwright base)
- [x] Rate limiter (token bucket per source) (shipped in Phase 1, reused by Playwright base)

### Originally planned server-side adapters — all TOS-blocked

  1. [~] ~~Rentals.ca~~ — TOS § 3.16 prohibits automated extraction (see `docs/legal.md`)
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
- [x] Document the legal posture in `docs/legal.md` — captured pages must be ones the user requested
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

- [ ] Save search UI
- [ ] Background job runner (APScheduler)
- [ ] Email notifier (SMTP)
- [ ] Web push notifications
- [ ] Alert dedup (don't notify twice for same listing)
- [ ] **Milestone:** Get an email when a new matching listing appears

## Phase 6: ~~Facebook Marketplace via Browser Extension~~ — folded into Phase 3

Originally a standalone phase. As of the Phase 3 pivot to user-driven capture, Facebook Marketplace is one of the per-site captures handled by the same extension architecture. See Phase 3.

## Phase 7: Map View, Split View & Mobile Polish (Week 11)
**Goal:** Add map and split views; make mobile experience excellent.

- [ ] Map view with MapLibre GL JS + OpenStreetMap tiles
- [ ] Marker clustering (`supercluster`)
- [ ] "Search this area" affordance after pan/zoom
- [ ] School catchment polygon overlay (toggleable)
- [ ] SkyTrain station radii overlay (toggleable)
- [ ] Split view (map + list, synced hover/selection state)
- [ ] Responsive design pass — list view default on mobile, split view default on wide desktop
- [ ] Filter persistence (URL params) so searches are shareable/bookmarkable
- [ ] PWA install support
- [ ] **Milestone:** Beautiful experience on iPhone Safari and large desktop alike

## Phase 8: macOS & iOS Native (Phase 2 territory)
**Goal:** Ship native apps using the same Expo codebase.

- [ ] Expo build for iOS
- [ ] Expo build for macOS (via Catalyst or native target)
- [ ] App Store / TestFlight distribution (if going public)

## Phase 9: Multi-user Hosted (Future)
**Goal:** Let others sign up and use it without self-hosting.

- [ ] Authentication (Auth.js / Clerk)
- [ ] Per-user encrypted credentials
- [ ] PostgreSQL + Meilisearch
- [ ] Per-user rate limit budgets
- [ ] Legal review before launch
- [ ] Reach out to platforms re: terms

## Open Questions

- ~~Should we build a "user-driven" mode where the user opens their own browser and RentWise observes their activity? (More like a Pinboard for rentals than a scraper.) This may be more legally bulletproof.~~ Resolved Phase 3 — that's exactly what the extension does.
- ~~Should we partner with one of the platforms (e.g. liv.rent is Vancouver-based and might be open to an integration)?~~ Cancelled — see the cancelled parallel track in Phase 3.
- Do we want to support the Vancouver short-term rental registry data?
