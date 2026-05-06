"""Tests for the POST /search router (Task F1)."""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command


@pytest.fixture
def client(monkeypatch, tmp_sqlite_url):
    monkeypatch.setenv("DATABASE_URL", tmp_sqlite_url)

    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", tmp_sqlite_url)

    # command.upgrade is sync but calls asyncio.run() internally via env.py.
    # Running it in a thread pool executor avoids conflicts with any running
    # event loop (the thread has no running loop, so asyncio.run() works fine).
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(command.upgrade, cfg, "head").result()

    # Reset cached engine/sessionmaker so the next call picks up the new URL.
    from rentwise.storage import db as dbmod

    dbmod.get_engine.cache_clear()
    dbmod.get_sessionmaker.cache_clear()

    from rentwise.settings import settings

    settings.database_url = tmp_sqlite_url

    from rentwise.main import create_app

    app = create_app()

    from rentwise.http.search import get_adapters

    app.dependency_overrides[get_adapters] = lambda: []

    with TestClient(app) as c:
        yield c


def test_search_validates_payload(client):
    """limit > 200 should return 422 validation error."""
    r = client.post("/search", json={"limit": 9999})
    assert r.status_code == 422


def test_search_empty_query_returns_200(client):
    """Empty query with no adapters returns a valid SearchResponse."""
    r = client.post("/search", json={"query": {}})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["cache_status"] == "miss"
    assert body["listings"] == []


def test_search_unsupported_filters_surfaced(client):
    """unsupported_filters key is present in the response."""
    r = client.post(
        "/search",
        json={"query": {"pets": "ok", "school_catchment": "Byng"}},
    )
    assert r.status_code == 200
    body = r.json()
    # No adapters registered → unsupported_filters is empty list (no adapter
    # to declare them unsupported), but the key must be present.
    assert "unsupported_filters" in body
