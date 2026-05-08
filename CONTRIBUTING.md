# Contributing to RentWise

Thanks for your interest! RentWise is in early development as a personal-use, self-hosted tool for Vancouver rentals. Contributions are welcome — especially on:

- New server-side source adapters that follow `docs/operational-rules.md`.
- Better dedup and enrichment.
- UI / UX improvements.
- Korean (한국어) translation polish.
- Documentation.

## Before contributing

1. **Read [`docs/operational-rules.md`](docs/operational-rules.md) carefully.** Any new adapter must follow these rate-limit / robots.txt / snippet rules. PRs that don't will be closed.
2. **Open a GitHub issue first**, then a PR. Describe scope + acceptance criteria in the issue; reference it in the PR (`Closes #N`). Even small chores get an issue — keeps the audit trail clean.
3. **Skim [`docs/roadmap.md`](docs/roadmap.md)** to find where your change fits.

## Workflow

1. **Issue first**, with scope + acceptance criteria.
2. **Branch**: `feat/<short-description>`, `fix/<...>`, `chore/<...>`, `docs/<...>`.
3. **Update docs in the same PR** — roadmap ticks, README source-table updates, etc.
4. **Conventional Commits**: `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`.
5. **CI must be green** before merge. The pipeline runs:
   - `apps/api`: ruff + mypy + pytest with coverage gate (≥85%).
   - `apps/web`: tsc + eslint + jest with coverage gate (≥80% statements / ≥75% branches) + Playwright E2E.
6. **PR body**: short summary, "what lands" table, decisions baked in, test plan checklist. Recent PRs in `git log` are good templates.

## Dev setup

See the [README Quick Start](README.md#quick-start). The short form:

```bash
git clone https://github.com/jfive-ai/rentwise
cd rentwise
cp .env.example .env
docker compose up
```

For per-app run / test commands without Docker, see:
- [`apps/api/README.md`](apps/api/README.md) — backend
- [`apps/web/README.md`](apps/web/README.md) — frontend

## Adding a new source adapter

The contract is `apps/api/rentwise/adapters/base.py` (`SourceAdapter` Protocol). Every adapter is server-side; the Phase 3 browser-extension capture path was retired in Phase 8 PR-B.

1. **Read [`docs/operational-rules.md`](docs/operational-rules.md).** It defines the rate-limit / robots.txt / snippet rules every adapter follows. Sources that require login or anti-bot evasion are out of scope — don't add an adapter, look for an official API instead.
2. **Create** `apps/api/rentwise/adapters/<name>/` with `__init__.py` and `adapter.py`.
3. **Implement** the `SourceAdapter` Protocol (`name`, `base_url`, `method`, `rate_limit_per_second`, `capabilities`, `search`, `fetch_listing`, `health_check`).
4. **Tests** in `apps/api/tests/adapters/test_<name>.py`. Use recorded fixtures (`vcrpy` / `respx`) — never hit the live source from CI.
5. **Honor `robots.txt`** and the rate-limit ceiling in [`docs/operational-rules.md`](docs/operational-rules.md) (≤ 1 req/sec, with random 500-1500 ms jitter, no parallel requests against the same source, honest `User-Agent`).
6. **Register** the adapter in `apps/api/rentwise/http/search.py::_build_adapters()`.
7. **Update** the README's Sources table and tick the matching row in `docs/roadmap.md`.

## Code style

- **Python:** ruff for lint + format (`ruff check .` then `ruff format .`). Type hints required (`mypy rentwise` clean). `structlog` for logging — never `print` or stdlib `logging`.
- **TypeScript:** ESLint + tsc strict. Functional components + hooks. `react-native` primitives (`View` / `Text` / `ScrollView`) for cross-platform compatibility.
- **Comments:** lead with *why*, not *what*. Don't reference past PRs / issues / fix tasks — those belong in the PR body and rot in code.
- **Don't add backwards-compat shims** for unreleased internal code. The repo is small; just change the call sites.

## Code review

- The repo's `/code-review` flow can run multi-agent reviews on PRs. Treat its output as a senior code-reviewer's first pass; defend or fix each finding in PR comments.
- For higher-stakes changes, `/codex:adversarial-review` provides an independent second opinion.

## Code of Conduct

Be kind. We're all here trying to find a place to live.
