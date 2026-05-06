"""End-to-end pipeline test. Uses recorded fixture, never live HTTP.

Covers cache miss → persist → cache hit → force refresh roundtrip plus
unsupported_filters wiring through the CL adapter.
"""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "craigslist"


@pytest.fixture
def stubbed_cl():
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://vancouver.craigslist.org/robots.txt").mock(
            return_value=Response(200, text=(FIX / "robots_txt_allowed.txt").read_text())
        )
        mock.get(url__regex=r"https://vancouver\.craigslist\.org/search/apa.*").mock(
            return_value=Response(200, content=(FIX / "sample_feed.rss").read_bytes())
        )
        yield mock


@pytest.fixture
def app_client(monkeypatch, tmp_sqlite_url, stubbed_cl):
    monkeypatch.setenv("DATABASE_URL", tmp_sqlite_url)

    from alembic.config import Config

    from alembic import command

    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", tmp_sqlite_url)

    # Run alembic upgrade in a thread so asyncio.run() inside env.py works fine
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(command.upgrade, cfg, "head").result()

    # Reset cached engine/sessionmaker so the next call picks up the new URL
    from rentwise.storage import db as dbmod

    dbmod.get_engine.cache_clear()
    dbmod.get_sessionmaker.cache_clear()

    from rentwise.settings import settings

    settings.database_url = tmp_sqlite_url

    from rentwise.main import create_app

    app = create_app()

    with TestClient(app) as c:
        yield c


@pytest.mark.integration
def test_full_search_pipeline(app_client, stubbed_cl):
    payload = {"query": {"bedrooms_min": 1}, "limit": 50}

    r = app_client.post("/search", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cache_status"] == "miss"
    assert body["total"] >= 1
    assert body["source_health"]["craigslist"]["status"] == "ok"

    initial_calls = sum(route.call_count for route in stubbed_cl.routes)

    r2 = app_client.post("/search", json=payload)
    body2 = r2.json()
    assert body2["cache_status"] == "fresh"
    after_cache_hit = sum(route.call_count for route in stubbed_cl.routes)
    assert after_cache_hit == initial_calls

    r3 = app_client.post("/search", json={**payload, "force_refresh": True})
    body3 = r3.json()
    assert body3["cache_status"] == "miss"
    after_force = sum(route.call_count for route in stubbed_cl.routes)
    assert after_force > after_cache_hit


@pytest.mark.integration
def test_unsupported_filters_surfaced(app_client):
    payload = {"query": {"pets": "ok", "school_catchment": "Byng"}}
    r = app_client.post("/search", json=payload)
    body = r.json()
    assert "pets" in body["unsupported_filters"]
    assert "school_catchment" in body["unsupported_filters"]
