# RentWise API

Python 3.12 + FastAPI backend. See the [root README](../../README.md) for the project overview and Quick Start.

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head        # migrations run from data/rentwise.db
uvicorn rentwise.main:app --reload
```

- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs

The first start creates `data/rentwise.db`. To wipe and reseed, delete the file and re-run `alembic upgrade head`.

## Lint + type check

```bash
ruff check .
ruff format .
mypy rentwise
```

## Tests

```bash
pytest                                # unit + property tests
pytest -m integration                 # end-to-end (recorded fixtures, no live HTTP)
pytest --cov=rentwise --cov-fail-under=85
```

Tests use an in-memory SQLite per case (file-backed under a tmp dir so Alembic can attach). All HTTP is mocked via `respx` / `vcrpy`; CI never touches a live source.

## Layout

```
rentwise/
├── adapters/          # Source adapters (Craigslist + Playwright base)
├── aggregator/        # /search orchestration + freshness / cache
├── capture/           # /capture endpoint for the browser extension (Phase 3)
├── dedup/             # Cross-source duplicate scoring (Phase 4)
├── enrichment/        # Address + geocode + catchment + transit + photo phash
├── http/              # FastAPI routers
│   ├── search.py
│   ├── searches.py    # Saved searches CRUD + /run-now (Phase 5)
│   └── ...
├── llm/               # LiteLLM wrapper + tool-use schema (Phase 2)
├── notifications/     # APScheduler + SMTP email + alert runner (Phase 5)
├── storage/           # SQLAlchemy ORM + repos
├── main.py            # FastAPI app factory + scheduler lifecycle hooks
└── settings.py        # Pydantic settings loaded from .env
```

## Settings

All settings come from environment variables / `.env`. See [`.env.example`](../../.env.example) for the full list, and [`rentwise/settings.py`](rentwise/settings.py) for the Pydantic schema.

Notable groups:

- `RENTWISE_LLM_*` — provider, fallback, timeout (Phase 2).
- `RENTWISE_GEOCODE_*` — Nominatim base URL, timeout, cache TTL (Phase 4 PR-A).
- `RENTWISE_PHOTO_HASH_*` / `RENTWISE_DEDUP_*` — phash + dedup tuning (Phase 4 PR-C).
- `RENTWISE_SCHEDULER_ENABLED` — set `true` to start the alert scheduler at app boot (Phase 5 PR-B).
- `RENTWISE_SMTP_*` + `RENTWISE_ALERTS_*` — SMTP relay credentials + sender + app base URL.

## Migrations

```bash
alembic revision -m "short message" --autogenerate
alembic upgrade head
alembic downgrade -1
```

Versions live under `alembic/versions/`. Current head: `0008_alerts`.

## Adding an endpoint

1. New router in `rentwise/http/<feature>.py` returning an `APIRouter` from `build_router()`.
2. `app.include_router(build_router())` in `rentwise/main.py::create_app`.
3. Tests in `tests/http/test_<feature>.py` using `fastapi.testclient.TestClient` with the standard fixture pattern (see `tests/http/test_searches.py` for a current example).
