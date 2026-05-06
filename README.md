# RentWise 🏡

> Natural-language rental search across every major Vancouver listing platform — in one place.

**Stop tab-switching between liv.rent, PadMapper, Zumper, Craigslist, and Facebook Marketplace.** Ask RentWise in plain English (or Korean!) what you want, and it queries every supported platform on your behalf using a mix of public APIs, RSS feeds, and ethical browser automation.

```
"2 bedroom apartment under $2800 in Sir Winston Churchill Secondary catchment, pet-friendly, available June"
```

→ aggregated results from all platforms, deduplicated, with one click to the original listing.

## Status

🚧 **Pre-alpha — under active development.** Vancouver, BC only for the MVP.

## Sources

| Source | Status | Method | Notes |
|---|---|---|---|
| Craigslist Vancouver | ✅ Shipped (Phase 1) | RSS | RSS-only per [legal.md](docs/legal.md#craigslist) |
| liv.rent | Planned (Phase 3) | Browser | |
| PadMapper | Planned (Phase 3) | Browser | |
| Zumper | Planned (Phase 3) | Browser | |
| Rentals.ca | Planned (Phase 3) | Browser | |
| REW.ca | Planned (Phase 3) | Browser | |
| Facebook Marketplace | Planned (Phase 6) | Browser extension | |

## Why RentWise?

Searching for a rental in Vancouver is exhausting:
- 6+ platforms to check daily
- Each has different filter syntax and quirks
- No way to search by school catchment, walk-to-SkyTrain time, or other practical criteria
- Lots of duplicate listings posted across multiple sites

RentWise solves this by:
1. **Aggregating** listings from every major platform into one searchable index
2. **Translating natural language** into per-platform queries via LLM
3. **Deduplicating** the same listing posted on multiple sites
4. **Enriching** with practical info (school catchment, transit access, walkability)
5. **Respecting platform Terms of Service** — only scrape what's legally permissible

## MVP Scope

- **Region:** Vancouver, BC
- **Use:** Personal (single-user, self-hosted)
- **Platforms targeted:**
  - liv.rent
  - PadMapper
  - Zumper
  - Rentals.ca
  - REW.ca
  - Craigslist Vancouver
  - Facebook Marketplace (research mode — see [docs/legal.md](docs/legal.md))

## Tech Stack

- **Backend:** Python 3.12 + FastAPI
- **Frontend:** React + Expo (web first, then iOS/macOS)
- **Database:** SQLite (MVP) → PostgreSQL (when scaling)
- **LLM:** [LiteLLM](https://docs.litellm.ai/) abstraction layer — works with OpenRouter (free + paid), Anthropic, OpenAI, Google, Ollama (local), or any other provider. User picks at first run.
- **Languages supported:** English & Korean (한국어) from day 1
- **Scraping:** Playwright (headless browser when needed) + httpx (when APIs/RSS available)
- **Search:** Local full-text search via SQLite FTS5 → Meilisearch (when scaling)

## Quick Start

```bash
# Clone
git clone https://github.com/ylee89/rentwise
cd rentwise

# Configure your LLM provider
cp .env.example .env
# Edit .env — at minimum, paste an OPENROUTER_API_KEY (free tier, no credit card)
# Sign up: https://openrouter.ai

# Run with Docker
docker compose up

# Open http://localhost:8081 — RentWise web app
# Open http://localhost:8000/docs — API documentation
```

### Run without Docker

**Backend:**
```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn rentwise.main:app --reload
```

**Frontend:**
```bash
cd apps/web
npm install
npm run web   # web at http://localhost:8081
npm run ios   # iOS simulator (requires Xcode)
```

## Repo Structure

```
rentwise/
├── apps/
│   ├── api/                 # Python + FastAPI backend
│   │   ├── rentwise/
│   │   │   ├── adapters/    # One module per rental source
│   │   │   ├── llm/         # LiteLLM wrapper
│   │   │   ├── models.py    # NormalizedQuery, Listing, etc.
│   │   │   ├── settings.py  # Pydantic settings
│   │   │   └── main.py      # FastAPI app
│   │   └── tests/
│   └── web/                 # React + Expo frontend (web/iOS/macOS)
│       └── app/             # expo-router screens
├── docs/
│   ├── specifications.md
│   ├── architecture.md
│   ├── llm-providers.md
│   ├── legal.md
│   └── roadmap.md
├── docker-compose.yml
└── .env.example

## Docs

- [Specifications](docs/specifications.md) — full app spec
- [Architecture](docs/architecture.md) — system design
- [LLM Providers](docs/llm-providers.md) — provider-agnostic LLM strategy
- [Legal & Ethics](docs/legal.md) — what we will and won't scrape, and why
- [Roadmap](docs/roadmap.md) — phased build plan
- [Contributing](CONTRIBUTING.md) — how to help

## License

MIT — see [LICENSE](LICENSE)

## Disclaimer

RentWise is an independent project, not affiliated with liv.rent, PadMapper, Zumper, Craigslist, Facebook, or any other listing platform. All listings remain the property of their original posters and the platforms hosting them. RentWise stores only public metadata and links back to the original source.
