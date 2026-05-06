# Contributing to RentWise

Thanks for your interest! RentWise is in early development. Right now the project is a one-person side project, but contributions are welcome — especially on:

- New source adapters
- Better dedup algorithms
- UI/UX improvements
- Translation (especially Korean, French)
- Documentation

## Before contributing

1. **Read [docs/legal.md](docs/legal.md) carefully.** Any new adapter must follow these rules. PRs that don't will be closed.
2. **Open an issue first** for non-trivial changes so we can discuss the approach.

## Dev setup

```bash
git clone https://github.com/<user>/rentwise
cd rentwise
docker compose up
```

(Detailed setup coming when there's something to set up.)

## Adding a new source adapter

1. Create `apps/api/adapters/<name>/`
2. Implement the `SourceAdapter` Protocol
3. Add a `selectors.yaml` if browser-based
4. Add tests in `apps/api/tests/adapters/test_<name>.py`
5. Update `docs/legal.md` with per-source notes
6. Update the README's source list

## Code style

- **Python:** ruff + black, type hints required
- **TypeScript:** eslint + prettier, strict mode
- **Commits:** Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, etc.)

## Testing

- Unit tests for adapters use recorded HTTP fixtures (VCR.py)
- Don't hit real platforms in CI — use fixtures
- Manual integration testing only, with throttling, against live sites

## Code of Conduct

Be kind. We're all here trying to find a place to live.
