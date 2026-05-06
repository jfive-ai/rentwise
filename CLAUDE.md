# CLAUDE.md

This file gives Claude Code the context it needs to work effectively on RentWise. Read it before making changes.

## What this project is

RentWise is a **natural-language rental search aggregator** for Vancouver, BC. Users type "2br Kitsilano under $3000 pet-friendly" (English or Korean) and get unified results from liv.rent, PadMapper, Zumper, Rentals.ca, REW.ca, Craigslist, and Facebook Marketplace.

It's a personal-use, self-hosted tool today. May become a hosted service later.

## Read these first

Before making non-trivial changes, read:

1. **`docs/specifications.md`** — what the app does
2. **`docs/architecture.md`** — how it's built
3. **`docs/legal.md`** — **non-negotiable** rules about scraping, rate limits, robots.txt
4. **`docs/llm-providers.md`** — the LLM-agnostic strategy
5. **`docs/roadmap.md`** — what's done, what's next

## Stack

- **Backend:** Python 3.12 + FastAPI + Pydantic + LiteLLM + Playwright + SQLite/aiosqlite
- **Frontend:** React + Expo Router (universal: web, iOS, macOS) + TypeScript
- **Infra:** Docker Compose for dev

## Repo layout

```
apps/
  api/                     # Backend
    rentwise/
      adapters/            # One subpackage per source (Phase 1+)
        base.py            # SourceAdapter Protocol
      llm/
        client.py          # LiteLLM wrapper
      models.py            # NormalizedQuery, RawListing, NormalizedListing
      settings.py          # Pydantic settings
      main.py              # FastAPI app + route registration
    tests/
  web/                     # Frontend
    app/                   # expo-router screens
docs/                      # Specs, architecture, legal
```

## Conventions

### Python
- **Type hints required everywhere.** Use modern syntax (`str | None`, `list[X]`).
- **Ruff** for linting + formatting (config in `pyproject.toml`). Run `ruff check .` and `ruff format .` before committing.
- **Pytest** for tests. Async tests work via `asyncio_mode = "auto"` in `pyproject.toml`.
- **structlog** for logging. Don't use `print` or stdlib `logging`.
- **Pydantic models** for all data crossing boundaries (HTTP, DB, LLM).
- **No `print` debugging** in committed code.

### TypeScript
- **Strict mode on.** Don't add `any` to silence the compiler — fix the type.
- **Functional components**, hooks-based state.
- **expo-router** for navigation (file-based routing in `app/`).
- **react-native primitives** (`View`, `Text`, `ScrollView`) for cross-platform compatibility — they render correctly on web, iOS, and macOS.

### Commit messages
Conventional Commits: `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`.

### Branching
- `main` is always green.
- Feature branches: `feat/short-description`, `fix/short-description`.

## Working on adapters (when we get to Phase 1+)

Every rental source is an adapter implementing the `SourceAdapter` Protocol in `apps/api/rentwise/adapters/base.py`. Rules — these are **non-negotiable**:

1. **Read `docs/legal.md` first.** It tells you what each source allows.
2. **Honor `robots.txt`.** Always.
3. **Rate limit:** `rate_limit_per_second <= 1.0`, with random 500–1500ms jitter between requests. Never parallel requests against the same source.
4. **Identify honestly** via the `User-Agent` from `settings.user_agent`.
5. **Store metadata only.** No verbatim long descriptions, no re-hosted photos. Snippets ≤200 chars.
6. **Tests use VCR fixtures.** Don't hit live sites in CI.

When adding a new adapter:
1. Create `apps/api/rentwise/adapters/<name>/` with `__init__.py`, `adapter.py`, optionally `selectors.yaml`.
2. Implement `SourceAdapter` (search, fetch_listing, health_check).
3. Add tests with recorded fixtures.
4. Update `docs/legal.md` with per-source notes.
5. Update README's source list.
6. Register the adapter in the aggregator's source registry.

## LLM work (Phase 2+)

- All LLM calls go through `apps/api/rentwise/llm/client.py`. Don't import `litellm` elsewhere.
- The `RENTWISE_LLM_MODEL` env var picks the provider. Code stays provider-agnostic.
- For NL → query parsing, use **tool use / structured output** — never parse free-form JSON from text.
- The system prompt is **bilingual** (Korean + English) and includes Vancouver neighborhoods, school catchments, SkyTrain stations.

## What's done (Phase 0)

- ✅ Repo structure
- ✅ FastAPI skeleton with `/health`, `/health/llm`, `/search` (stub), `/translate-query` (stub)
- ✅ Pydantic models (`NormalizedQuery`, `RawListing`, `NormalizedListing`, etc.)
- ✅ `SourceAdapter` Protocol
- ✅ LiteLLM client wrapper (stub for `translate_query`)
- ✅ Expo Universal app with home screen showing system status
- ✅ Docker Compose
- ✅ CI (GitHub Actions)
- ✅ All docs

## What's next (Phase 1 — Craigslist adapter)

In order:

1. Define DB schema and migrations (Alembic). Tables: `listings`, `canonical_listings`, `searches`, `alerts`, `users`, `source_health`.
2. Implement `apps/api/rentwise/adapters/craigslist/` using **the RSS feed** (not HTML).
   - URL pattern: `https://vancouver.craigslist.org/search/apa?format=rss&...`
   - Use `feedparser` for parsing.
3. Implement an aggregator that calls one or more adapters and writes results to SQLite.
4. Replace the `/search` stub with a real handler.
5. Build the filter UI on the frontend (no NL yet) — see `docs/specifications.md` § 3.1 Mode B.
6. Build the results display with **card grid** + **list/table** views — see `docs/specifications.md` § 3.2.

## Don't do these things

- ❌ Don't hit live rental sites from tests. Use VCR fixtures.
- ❌ Don't add adapters for paid/locked content (login walls, paywalls).
- ❌ Don't increase rate limits beyond 1 req/sec without a really good reason.
- ❌ Don't store verbatim listing descriptions or re-host photos.
- ❌ Don't add `localStorage` or browser-only APIs without thinking about iOS/macOS targets.
- ❌ Don't `npm install` packages without checking they support both web and React Native.

## Things that aren't obvious

- **Why filter UI ships before NL:** Phase 1's filter UI works *without* the LLM. This means the app is usable on day 1 even before any LLM is configured, and the LLM becomes a UX layer on top, not a hard dependency.
- **Why dedup runs after enrichment:** address normalization (which feeds dedup) needs the geocoded coordinates that enrichment provides.
- **Why we use SQLite for MVP:** zero-config, zero-deps, FTS5 is excellent. We'll graduate to Postgres + Meilisearch when we need multi-user.
- **Why MapLibre over Mapbox:** no API key, no quota, OpenStreetMap is free. Mapbox is a future upgrade if we need their tile quality.

## Useful commands

```bash
# Backend
cd apps/api
uvicorn rentwise.main:app --reload     # dev server
pytest                                  # tests
ruff check . && ruff format .          # lint

# Frontend
cd apps/web
npm run web                             # web dev server
npm run ios                             # iOS simulator
npx tsc --noEmit                        # type check

# Both
docker compose up                       # full stack
docker compose logs -f api              # tail backend logs
```

## Korean text handling

Korean is supported from day 1. When writing code that handles user input:

- Don't assume ASCII or Latin-1.
- Use `str` (Python) / `string` (TS) — both are Unicode by default.
- For full-text search, SQLite's FTS5 with the `unicode61` tokenizer handles Korean.
- The LLM system prompt should explicitly say it can receive input in Korean OR English and should output the same structured query regardless.
