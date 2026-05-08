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
├── adapters/          # Craigslist (RSS) + Playwright base + Phase 8 scaffolds
│   ├── craigslist/    # Shipped (RSS only)
│   ├── rentalsca/     # Phase 8 PR-C scaffold — RENTWISE_RENTALSCA_ENABLED
│   ├── padmapper/     # Phase 8 PR-D scaffold — RENTWISE_PADMAPPER_ENABLED
│   ├── zumper/        # Phase 8 PR-E scaffold — RENTWISE_ZUMPER_ENABLED
│   ├── rew/           # Phase 8 PR-E scaffold — RENTWISE_REW_ENABLED
│   ├── livrent/       # Phase 8 PR-E scaffold — RENTWISE_LIVRENT_ENABLED
│   └── ...
├── aggregator/        # /search orchestration + freshness / cache
├── dedup/             # Cross-source duplicate scoring (Phase 4)
├── enrichment/        # Address + geocode + catchment + transit + photo phash
├── http/              # FastAPI routers
│   ├── search.py
│   ├── searches.py    # Saved searches CRUD + /run-now (Phase 5 PR-A/B)
│   ├── web_push.py    # VAPID public key + subscription CRUD (Phase 5 PR-C)
│   └── map_overlays.py # School-catchment + SkyTrain GeoJSON for Phase 7 PR-B
├── llm/               # LiteLLM wrapper + tool-use schema (Phase 2)
├── notifications/     # APScheduler + SMTP email + web push + alert runner (Phase 5)
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
- `RENTWISE_WEB_PUSH_ENABLED` + `RENTWISE_VAPID_*` — VAPID keypair + contact for browser push (Phase 5 PR-C).
- `RENTWISE_RENTALSCA_ENABLED` / `RENTWISE_PADMAPPER_ENABLED` / `RENTWISE_ZUMPER_ENABLED` / `RENTWISE_REW_ENABLED` / `RENTWISE_LIVRENT_ENABLED` — Phase 8 direct-adapter opt-in flags. **Default `false`**; selectors not yet calibrated to live markup. Read `docs/operational-rules.md` "Source notes" before flipping any of these on.

## Migrations

```bash
alembic revision -m "short message" --autogenerate
alembic upgrade head
alembic downgrade -1
```

Versions live under `alembic/versions/`. Current head: `0010_drop_capture` (the Phase 8 PR-B revision that drops the retired `captures` table).

## Adding an endpoint

1. New router in `rentwise/http/<feature>.py` returning an `APIRouter` from `build_router()`.
2. `app.include_router(build_router())` in `rentwise/main.py::create_app`.
3. Tests in `tests/http/test_<feature>.py` using `fastapi.testclient.TestClient` with the standard fixture pattern (see `tests/http/test_searches.py` for a current example).
