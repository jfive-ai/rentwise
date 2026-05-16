# RentWise 🏡

> Natural-language rental search across every major Vancouver listing platform — in one place.

**Stop tab-switching between Rentals.ca, PadMapper, Zumper, REW.ca, liv.rent, Craigslist, and Facebook Marketplace.** Ask RentWise in plain English (or Korean!) what you want, and it surfaces unified results across every supported platform.

```
"2 bedroom apartment under $2800 in Lord Byng catchment, pet-friendly, available June"
```

→ aggregated results from all platforms, deduplicated, with one click to the original listing — and an email alert when new matches appear.

## Status

🚧 **Pre-alpha — under active development.** Vancouver, BC only.

**Personal-use tool, not a service.** RentWise runs locally on a single machine for the person who installed it. It is not hosted for other users, not sold, and not redistributed. See [`docs/operational-rules.md`](docs/operational-rules.md) for the rules every adapter follows (rate limits, `robots.txt`, snippet caps, no re-hosting photos) so the project stays a polite citizen of the sites it queries.

**Phases shipped:**

- ✅ Phase 0 — Foundations
- ✅ Phase 1 — Craigslist adapter + filter UI + card / list views
- ✅ Phase 2 — Natural-language search (English + Korean) with first-run LLM wizard
- ⊘ Phase 3 — Browser extension (retired in Phase 8 PR-B; replaced by direct adapters)
- ✅ Phase 4 — Address normalization + geocoding + school catchments + transit + photo perceptual hashing + cross-source dedup + UI polish
- ✅ Phase 5 — Saved searches + APScheduler + SMTP email alerts + dedup ledger + web push notifications
- ✅ Phase 7 — Map view + clustering + catchment & SkyTrain overlays + split view + viewport-aware default + URL filter persistence + PWA
- 🚧 Phase 8 — macOS app shipped (Electron at `apps/desktop/`, build via `scripts/build-mac.sh`); browser extension retired; direct adapters for Rentals.ca, PadMapper, Zumper, REW.ca, liv.rent landed as **scaffolds disabled by default** — selectors require live-markup calibration before real results flow

## Sources

| Source | Method | Status | Notes |
|---|---|---|---|
| Craigslist Vancouver | RSS, server-side | ✅ Shipped | RSS-only per [operational-rules.md § Craigslist](docs/operational-rules.md#craigslist) |
| Rentals.ca | Direct adapter (Phase 8 PR-C) | 🚧 Scaffold, disabled by default | URL builder + robots.txt + selector skeleton land; selectors not yet calibrated to live markup. Set `RENTWISE_RENTALSCA_ENABLED=true` to register the adapter. |
| PadMapper | Direct adapter (Phase 8 PR-D) | 🚧 Scaffold, disabled by default | URL builder + robots.txt + `box=` guard land; `_extract` is a stub. Set `RENTWISE_PADMAPPER_ENABLED=true` to register. |
| Zumper | Direct adapter (Phase 8 PR-E) | 🚧 Scaffold, disabled by default | `_extract` returns `[]` until real selectors land. Set `RENTWISE_ZUMPER_ENABLED=true` to register. |
| REW.ca | Direct adapter (Phase 8 PR-E) | 🚧 Scaffold, disabled by default | TOS is the most explicit anti-scraping language of any source we considered — opting in is a deliberate choice. `RENTWISE_REW_ENABLED=true`. |
| liv.rent | Direct adapter (Phase 8 PR-E) | 🚧 Scaffold, disabled by default | Vancouver-based; partnership is the preferred long-term path. `RENTWISE_LIVRENT_ENABLED=true`. |
| Facebook Marketplace | Out of scope | ❌ Login-walled — no automated login per `docs/operational-rules.md` | Use the platform directly |

> **Phase 8 pivot** — the user-driven browser extension that previously covered Rentals.ca, PadMapper, Zumper, REW.ca, liv.rent, and Facebook Marketplace was retired because it was inconvenient in daily personal use. Direct adapters (PR-C/D/E) replace it; Facebook Marketplace stays out of scope because it's login-walled and we never automate logins. See `docs/roadmap.md` Phase 8.

## Why RentWise?

Searching for a rental in Vancouver is exhausting:
- 7 platforms to check daily
- Each has different filter syntax and quirks
- No way to search by school catchment, walk-to-SkyTrain time, or other practical criteria
- Lots of duplicate listings posted across multiple sites

RentWise solves this by:
1. **Aggregating** listings from every major platform into one searchable index.
2. **Translating natural language** (English and Korean) into per-platform queries via LLM.
3. **Enriching** with practical info — school catchments (VSB), nearest SkyTrain stop, walking minutes.
4. **Deduplicating** the same listing posted on multiple sites via address + price + photo perceptual hash.
5. **Notifying** you by email when a new matching listing appears (saved searches + APScheduler).
6. **Respecting platform rate limits + robots.txt** per [`docs/operational-rules.md`](docs/operational-rules.md) — login-walled sites stay out of scope.

## Tech Stack

- **Backend:** Python 3.12 + FastAPI + Pydantic + SQLite (FTS5 + Alembic) + APScheduler.
- **Frontend:** React + Expo Router (universal: web, iOS, macOS) + TypeScript strict.
- **LLM:** [LiteLLM](https://docs.litellm.ai/) abstraction — OpenRouter (free tier), Anthropic, OpenAI, Google, Ollama (local), or any other provider. User picks at first run.
- **Languages supported:** English & Korean (한국어) from day 1.
- **Enrichment:** [`pyap`](https://github.com/vladimarius/pyap) for address parsing, [Nominatim](https://nominatim.openstreetmap.org/) for geocoding (free; 1 req/sec), [`shapely`](https://shapely.readthedocs.io/) for VSB catchment polygons, haversine over a slim TransLink GTFS extract for transit walk minutes, [`imagehash`](https://github.com/JohannesBuchner/imagehash) `phash` for cross-source photo dedup.
- **Notifications:** SMTP via stdlib `smtplib`; web push via VAPID + service worker (`pywebpush` + `apps/web/public/sw.js`).
- **Map:** [MapLibre GL JS](https://maplibre.org/) + OpenStreetMap tiles, client-side clustering via [`supercluster`](https://github.com/mapbox/supercluster).
- **Desktop:** Electron shell at `apps/desktop/` that wraps the Expo web export as a real macOS `.app`.

## Quick Start

### 1. Clone + configure

```bash
git clone https://github.com/jfive-ai/rentwise
cd rentwise

cp .env.example .env
# Edit .env — at minimum, paste an OPENROUTER_API_KEY (free tier).
# Sign up: https://openrouter.ai
```

### 2. Run with Docker (recommended)

```bash
docker compose up
```

- API: http://localhost:8000 (Swagger UI at http://localhost:8000/docs)
- Web app: http://localhost:8081

### 3. First-run LLM wizard

The first time you open the web app, you'll be asked which LLM provider to use.
The default is a free OpenRouter model that works without a paid account; you can change this any time at **Settings → LLM**.

You can now use the app with **just Craigslist** as a source — that's enough to verify the end-to-end pipeline.

### Demo mode (no network required)

Want to see the full pipeline (search → aggregate → enrich → render) without
hitting any live site? Start the API with `RENTWISE_DEMO_MODE=true` and every
source is backed by the bundled test fixture instead of a network call:

```bash
RENTWISE_DEMO_MODE=true uvicorn rentwise.main:app --reload
```

You'll get ~15 fixture listings spread across all six sources
(craigslist, liv.rent, rentals_ca, padmapper, zumper, rew) with `source_health` =
`ok` for each. Useful for offline development, CI smoke tests, and the
end-to-end screenshots in `docs/screenshots/`.

### 4. Saved searches + email alerts (optional)

1. Run a search you'd like to keep tracking.
2. Click ★ **Save** on the results toolbar, fill in a label and (optionally) an email address, toggle **Email me when new listings match**.
3. Configure SMTP in `.env` (see [`.env.example`](.env.example)) and start the scheduler:
   ```bash
   RENTWISE_SCHEDULER_ENABLED=true docker compose up
   ```
4. Or trigger a manual test run via `POST /searches/{cache_key}/run-now`.
5. New matching listings → one email per dispatch, deduped via the `alert_log` table so you never get the same listing twice.

## Build the macOS app

Phase 8 packages RentWise as a real `.app` bundle so you can launch it from your dock. The wrapper is a tiny [Tauri v2](https://tauri.app/) shell in [`apps/desktop/`](apps/desktop) that loads the Expo web build — 100% of the TypeScript source is shared with the web app.

### One-time prereqs

- macOS on Apple Silicon.
- Node 20+.
- Rust toolchain — `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh` if you don't have it.

### Dev mode

```bash
make macos    # starts API + Expo web + Tauri together; Ctrl+C cleans up everything
```

### Production build

```bash
make setup-desktop    # first time only: ~5 min Rust compile
cd apps/desktop && npm run tauri build
```

`tauri build` runs `expo export -p web` automatically (via `beforeBuildCommand` in `src-tauri/tauri.conf.json`), then bundles the static output into `apps/desktop/src-tauri/target/release/bundle/macos/RentWise.app`.

The app expects the FastAPI backend at `http://localhost:8000` (configurable via `extra.apiBaseUrl` in `apps/web/app.json`). Run `make api` or `docker compose up` for the API before launching.

## Run without Docker

**Backend:**

```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn rentwise.main:app --reload   # http://localhost:8000
```

Tests / lint:
```bash
pytest                          # unit + property tests
pytest -m integration           # end-to-end with recorded fixtures
ruff check . && ruff format .
mypy rentwise
```

**Frontend:**

```bash
cd apps/web
npm install
npm run web         # web at http://localhost:8081
npm run ios         # iOS simulator (requires Xcode)
```

Tests / lint:
```bash
npm run typecheck
npm run lint
npm test                  # Jest unit/component tests
npm run test:coverage     # with coverage report
npx playwright install    # one-time: download browsers for E2E
npx playwright test       # E2E
```

## Repo Structure

```
rentwise/
├── apps/
│   ├── api/                       # Python + FastAPI backend
│   │   ├── alembic/               # DB migrations (head: 0010_drop_capture)
│   │   └── rentwise/
│   │       ├── adapters/          # Craigslist (RSS) + Playwright base + Phase 8 scaffolds
│   │       │                        # (rentalsca, padmapper, zumper, rew, livrent —
│   │       │                        #  all gated behind per-source RENTWISE_*_ENABLED flags)
│   │       ├── aggregator/        # /search orchestration + freshness / cache
│   │       ├── dedup/             # Cross-source duplicate scoring (Phase 4)
│   │       ├── enrichment/        # Address, geocode, catchment, transit, phash
│   │       ├── http/              # FastAPI routers (search, searches, web_push, map_overlays)
│   │       ├── llm/               # LiteLLM wrapper + tool-use schema
│   │       ├── notifications/     # APScheduler + email + web push + alert runner
│   │       └── storage/           # ORM + repos
│   ├── web/                       # React + Expo Router (universal: web/iOS/macOS)
│   │   ├── app/                   # expo-router screens
│   │   ├── public/                # PWA manifest + service worker
│   │   └── src/
│   │       ├── api/               # ApiClient + types
│   │       ├── components/        # FilterPanel, ListingCard, MapView, SaveSearchForm, ...
│   │       ├── screens/           # SearchScreen, SettingsScreen, FirstRunWizard
│   │       └── state/             # QueryProvider
│   └── desktop/                   # Electron shell that wraps apps/web/dist as RentWise.app
├── docs/
│   ├── architecture.md
│   ├── operational-rules.md      # Rate limits, robots.txt, snippet caps. Read before adding adapters.
│   ├── llm-providers.md
│   ├── roadmap.md
│   └── specifications.md
├── docker-compose.yml
├── Makefile
└── .env.example
```

## Docs

- [Roadmap](docs/roadmap.md) — phased build plan, what's shipped vs in-flight.
- [Operational rules](docs/operational-rules.md) — rate limits, robots.txt, snippet caps. **Read before adding any adapter.**
- [Architecture](docs/architecture.md) — system design.
- [LLM Providers](docs/llm-providers.md) — provider-agnostic LLM strategy.
- [Specifications](docs/specifications.md) — full feature spec.
- [Contributing](CONTRIBUTING.md) — workflow rules + how to add a source.

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

RentWise is an independent project, not affiliated with Rentals.ca, PadMapper, Zumper, REW.ca, liv.rent, Craigslist, Facebook, or any other listing platform. All listings remain the property of their original posters and the platforms hosting them. RentWise stores only public metadata + URLs (never photo bytes, never landlord contact info beyond a link) and follows the rate-limit / robots.txt rules in [`docs/operational-rules.md`](docs/operational-rules.md).
