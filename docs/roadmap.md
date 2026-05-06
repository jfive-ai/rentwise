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

- [ ] Define `SourceAdapter` Protocol
- [ ] Implement `CraigslistAdapter` using the RSS feed
- [ ] Define `RawListing`, `NormalizedListing`, and `NormalizedQuery` data models
- [ ] SQLite schema + migrations (Alembic)
- [ ] Aggregator that calls one adapter
- [ ] **Frontend: filter-based search UI** (faceted controls, no NL yet)
- [ ] **Frontend: results display with two views — card grid (default) + list/table**
- [ ] **Frontend: per-card actions — save / hide / contacted / open original**
- [ ] **Frontend: sort controls (newest, price asc/desc, bedrooms)**
- [ ] **Milestone:** Search Craigslist Vancouver with structured filters, switch between card/list views

## Phase 2: Natural Language Layer (Week 4)
**Goal:** Add NL search **on top of** the existing filter UI — bilingual (English + Korean) from day 1. Both modes coexist; users can switch at will.

- [ ] LiteLLM integration with provider-agnostic config
- [ ] First-run setup wizard (LLM provider + API key)
- [ ] Settings UI for switching LLM at runtime
- [ ] Tool-use schema for query translation (works across Anthropic/OpenAI/Google/OpenRouter)
- [ ] Bilingual system prompt (Korean + English) with Vancouver-specific neighborhoods, schools, SkyTrain
- [ ] **Frontend: NL search bar above the filter UI** + parsed-query preview with editable chips
- [ ] **Frontend: mode toggle** — "Natural language" ⇄ "Filters" — sharing the same NormalizedQuery state
- [ ] **Frontend: graceful fallback** — if LLM fails, show filter UI with friendly message
- [ ] Test against free OpenRouter models (Qwen 2.5, Llama 3.3) for both languages
- [ ] **Milestone:** "Find me a 2 bedroom in East Van under $2500" works
- [ ] **Milestone:** "이스트 밴 2베드 2500불 이하" works equally well
- [ ] **Milestone:** Switching from NL to filter view preserves the parsed query

## Phase 3: More Sources (Week 5-6)
**Goal:** Add browser-based adapters with rate limiting and robots.txt respect.

- [ ] Playwright adapter base class
- [ ] `robots.txt` parser & cache
- [ ] Rate limiter (token bucket per source)
- [ ] Implement adapters in this order (easiest to hardest):
  1. [ ] Rentals.ca
  2. [ ] PadMapper
  3. [ ] REW.ca
  4. [ ] Zumper
  5. [ ] liv.rent
- [ ] **Milestone:** Search across 6 sources from one query

## Phase 4: Deduplication & Enrichment (Week 7)
**Goal:** Useful, clean results.

- [ ] Address normalization (using `libpostal` or similar)
- [ ] Photo perceptual hashing (`imagehash`)
- [ ] Dedup matching algorithm + confidence scoring
- [ ] School catchment lookup (VSB shapefiles)
- [ ] Transit lookup (TransLink GTFS or Google Maps API)
- [ ] **Milestone:** "2br in Lord Byng catchment" works correctly

## Phase 5: Saved Searches & Alerts (Week 8)
**Goal:** Stop refreshing; let RentWise notify you.

- [ ] Save search UI
- [ ] Background job runner (APScheduler)
- [ ] Email notifier (SMTP)
- [ ] Web push notifications
- [ ] Alert dedup (don't notify twice for same listing)
- [ ] **Milestone:** Get an email when a new matching listing appears

## Phase 6: Facebook Marketplace via Browser Extension (Week 9-10)
**Goal:** Capture FB listings without violating their TOS.

- [ ] Chrome extension scaffold
- [ ] Content script that detects Marketplace listing pages
- [ ] Extract data from pages the user is *already viewing*
- [ ] Send to local RentWise API
- [ ] Clear UX: extension only activates when user is on Marketplace
- [ ] **Milestone:** Browse FB Marketplace normally → listings appear in RentWise

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

- Should we build a "user-driven" mode where the user opens their own browser and RentWise observes their activity? (More like a Pinboard for rentals than a scraper.) This may be more legally bulletproof.
- Should we partner with one of the platforms (e.g. liv.rent is Vancouver-based and might be open to an integration)?
- Do we want to support the Vancouver short-term rental registry data?
