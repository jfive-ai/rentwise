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
- ✅ Phase 3 — User-driven browser extension capturing 6 sources
- ✅ Phase 4 — Address normalization + geocoding + school catchments + transit + photo perceptual hashing + cross-source dedup + UI polish
- ✅ Phase 5 (PR-A + PR-B) — Saved searches + APScheduler + SMTP email alerts + dedup ledger
- ⏳ Phase 5 PR-C — Web push notifications
- ⏳ Phase 7 — Map view, split view
- ⏳ Phase 8 — macOS / iOS native via Expo

## Sources

| Source | Method | Status | Notes |
|---|---|---|---|
| Craigslist Vancouver | RSS, server-side | ✅ Shipped | RSS-only per [operational-rules.md § Craigslist](docs/operational-rules.md#craigslist) |
| Rentals.ca | Browser extension (user-driven) | ✅ Shipped | Captures pages the user already views in their own session |
| PadMapper | Browser extension (user-driven) | ✅ Shipped | Captures pages the user already views in their own session |
| Zumper | Browser extension (user-driven) | ✅ Shipped | Captures pages the user already views in their own session |
| REW.ca | Browser extension (user-driven) | ✅ Shipped | Captures pages the user already views in their own session |
| liv.rent | Browser extension (user-driven) | ✅ Shipped | Captures pages the user already views in their own session |
| Facebook Marketplace | Browser extension (user-driven) | ✅ Shipped | Login-walled; extension reads pages the user already views |

> **Phase 8 pivot in progress** — the browser extension is being retired in favor of direct adapters that run inside the macOS app, since the extension was inconvenient in practice for a personal-use install. See `docs/roadmap.md` Phase 8.

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
6. **Respecting platform Terms of Service** — only scrape what's legally permissible, capture the rest in the user's own browser.

## Tech Stack

- **Backend:** Python 3.12 + FastAPI + Pydantic + SQLite (FTS5 + Alembic) + APScheduler.
- **Frontend:** React + Expo Router (universal: web, iOS, macOS) + TypeScript strict.
- **Browser extension:** Chrome MV3 (Vite + React + zod). One content script per site; passive capture only.
- **LLM:** [LiteLLM](https://docs.litellm.ai/) abstraction — OpenRouter (free tier), Anthropic, OpenAI, Google, Ollama (local), or any other provider. User picks at first run.
- **Languages supported:** English & Korean (한국어) from day 1.
- **Enrichment:** [`pyap`](https://github.com/vladimarius/pyap) for address parsing, [Nominatim](https://nominatim.openstreetmap.org/) for geocoding (free; 1 req/sec), [`shapely`](https://shapely.readthedocs.io/) for VSB catchment polygons, haversine over a slim TransLink GTFS extract for transit walk minutes, [`imagehash`](https://github.com/JohannesBuchner/imagehash) `phash` for cross-source photo dedup.
- **Notifications:** SMTP via stdlib `smtplib`. Web push (Phase 5 PR-C) is in progress.

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

### 4. Browser extension (optional, but unlocks 6 more sources)

To pull listings from Rentals.ca, PadMapper, Zumper, REW.ca, liv.rent, and Facebook Marketplace, sideload the capture extension:

```bash
cd apps/extension
npm install
npm run build
```

Then in Chrome / Brave / Edge:

1. Open `chrome://extensions`, toggle **Developer mode** on.
2. **Load unpacked** → pick `apps/extension/dist`.
3. Pin **RentWise Capture** from the puzzle icon, right-click → **Options**.
4. In the web app, open **Settings → Browser extension**, copy the API URL + token, paste into the extension's options page, click **Save & validate**.
5. Browse any of the six sites normally — listings land in RentWise's results within seconds.

Full extension docs (sideload steps, fixture refresh, what's never captured): [`apps/extension/README.md`](apps/extension/README.md).

### 5. Saved searches + email alerts (optional)

1. Run a search you'd like to keep tracking.
2. Click ★ **Save** on the results toolbar, fill in a label and (optionally) an email address, toggle **Email me when new listings match**.
3. Configure SMTP in `.env` (see [`.env.example`](.env.example)) and start the scheduler:
   ```bash
   RENTWISE_SCHEDULER_ENABLED=true docker compose up
   ```
4. Or trigger a manual test run via `POST /searches/{cache_key}/run-now`.
5. New matching listings → one email per dispatch, deduped via the `alert_log` table so you never get the same listing twice.

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

**Extension:**

```bash
cd apps/extension
npm install
npm run typecheck
npm test            # vitest + jsdom
npm run build
```

## Repo Structure

```
rentwise/
├── apps/
│   ├── api/                       # Python + FastAPI backend
│   │   ├── alembic/               # DB migrations (head: 0008)
│   │   └── rentwise/
│   │       ├── adapters/          # Source adapters (Craigslist + Playwright base)
│   │       ├── aggregator/        # /search orchestration
│   │       ├── capture/           # /capture endpoint for the extension
│   │       ├── dedup/              # Cross-source duplicate scoring (Phase 4)
│   │       ├── enrichment/        # Address, geocode, catchment, transit, phash
│   │       ├── http/              # FastAPI routers
│   │       ├── llm/               # LiteLLM wrapper + tool-use schema
│   │       ├── notifications/     # APScheduler + email + alert runner
│   │       └── storage/           # ORM + repos
│   ├── web/                       # React + Expo Router (universal: web/iOS/macOS)
│   │   ├── app/                   # expo-router screens
│   │   └── src/
│   │       ├── api/               # ApiClient + types
│   │       ├── components/        # FilterPanel, ListingCard, SaveSearchForm, ...
│   │       ├── launcher/          # "Search across sources" launcher (Phase 3)
│   │       ├── screens/           # SearchScreen, SettingsScreen, FirstRunWizard
│   │       └── state/             # QueryProvider
│   └── extension/                 # Chrome MV3 capture extension (Phase 3)
│       └── src/                   # background worker, popup, options, content scripts
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
- [Browser extension](apps/extension/README.md) — sideload, fixture refresh, capture rules.
- [Contributing](CONTRIBUTING.md) — workflow rules + how to add a source.

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

RentWise is an independent project, not affiliated with Rentals.ca, PadMapper, Zumper, REW.ca, liv.rent, Craigslist, Facebook, or any other listing platform. All listings remain the property of their original posters and the platforms hosting them. RentWise stores only public metadata + URLs (never photo bytes, never landlord contact info beyond a link), and only ever captures pages the user themselves caused the browser to load.
