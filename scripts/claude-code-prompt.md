# Claude Code prompt — paste this when starting a new local session

I'm working on **RentWise**, a natural-language rental search aggregator for Vancouver, BC. I'm Yoonju (Korean speaker, recent UX/UI grad in Vancouver). The project lives at `/Users/yoonjulee/projects/rentwise`.

## Read these first, in order:

1. `CLAUDE.md` — your working agreement on this repo (conventions, what's done, what's next, what NOT to do)
2. `README.md` — quick start
3. `docs/specifications.md` — what the app does
4. `docs/architecture.md` — how it's built
5. `docs/legal.md` — **non-negotiable** rules about scraping, robots.txt, rate limits
6. `docs/llm-providers.md` — LLM-agnostic strategy (LiteLLM + OpenRouter free tier as default)
7. `docs/roadmap.md` — what's done vs next

## Current state

**Phase 0 is complete:** repo skeleton with FastAPI backend (stub endpoints), Expo Universal frontend (web/iOS/macOS), Docker Compose, CI, all docs. Tests pass, lint passes.

**Next up: Phase 1 — Craigslist adapter via RSS.** This is the easiest, lowest-legal-risk first source. The plan in `docs/roadmap.md`:

1. DB schema + Alembic migrations (`listings`, `canonical_listings`, `searches`, `alerts`, `users`, `source_health`)
2. Craigslist adapter using `feedparser` against `vancouver.craigslist.org/search/apa?format=rss&...`
3. Aggregator that calls one or more adapters and persists results
4. Replace `/search` stub with real handler
5. Frontend filter UI (no NL yet) — see `docs/specifications.md` § 3.1 Mode B
6. Frontend results display — card grid + list/table views — see `docs/specifications.md` § 3.2

## Working preferences

- Korean is supported from day 1 — never assume English-only input
- I'm comfortable with TypeScript/JavaScript, learning Python and Git/GitHub workflows
- I appreciate clear explanations of *why*, not just what
- Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `test:`)
- Don't `npm install` packages that don't work in both web and React Native
- Don't increase rate limits, don't bypass robots.txt, don't store verbatim listing content (see `docs/legal.md`)

## Where to start

Suggest: begin with the DB schema and Alembic setup, then Craigslist adapter, then wire up `/search`. Show me the plan before writing code, and break work into small commits I can review one at a time.
