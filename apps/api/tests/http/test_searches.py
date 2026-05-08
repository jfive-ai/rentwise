"""Tests for the /searches REST endpoints (Phase 5 PR-A)."""

from __future__ import annotations

import concurrent.futures
import json
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
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(command.upgrade, cfg, "head").result()

    from rentwise.storage import db as dbmod

    dbmod.get_engine.cache_clear()
    dbmod.get_sessionmaker.cache_clear()

    from rentwise.settings import settings

    settings.database_url = tmp_sqlite_url

    from rentwise.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


async def _seed_cache_row(tmp_sqlite_url: str, query_dict: dict) -> str:
    """Use the actual SearchRepo to seed an unsaved cache row, return its key."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from rentwise.aggregator.freshness import cache_key as compute_key
    from rentwise.models import NormalizedQuery
    from rentwise.storage.repositories import CachedSearch, SearchRepo

    q = NormalizedQuery(**query_dict)
    key = compute_key(q)
    engine = create_async_engine(tmp_sqlite_url)
    sessmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessmaker() as session:
        repo = SearchRepo(session)
        await repo.upsert(
            CachedSearch(
                cache_key=key,
                query_json=q.model_dump_json(),
                listing_ids=["a", "b"],
                total_count=2,
                is_saved=False,
            )
        )
        await session.commit()
    await engine.dispose()
    return key


def test_post_save_404_when_no_cache_row(client):
    body = {
        "query": {"bedrooms_min": 2, "neighborhoods": [], "free_text_keywords": []},
        "label": "2br",
    }
    r = client.post("/searches", json=body)
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert detail["error"] == "not_in_cache"


def test_post_save_then_get_then_delete_roundtrip(client, tmp_sqlite_url):
    import asyncio

    query = {"bedrooms_min": 2, "price_max": 3000, "neighborhoods": ["Kitsilano"]}
    key = asyncio.run(_seed_cache_row(tmp_sqlite_url, query))

    # Save
    r = client.post(
        "/searches",
        json={
            "query": {**query, "free_text_keywords": []},
            "label": "Kits 2br",
            "alert_enabled": True,
            "alert_email": "me@example.com",
            "cadence_minutes": 30,
        },
    )
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["cache_key"] == key
    assert saved["label"] == "Kits 2br"
    assert saved["alert_enabled"] is True
    assert saved["alert_email"] == "me@example.com"
    assert saved["cadence_minutes"] == 30

    # List
    r = client.get("/searches")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["cache_key"] == key
    assert items[0]["query"]["neighborhoods"] == ["Kitsilano"]

    # Delete
    r = client.delete(f"/searches/{key}")
    assert r.status_code == 204

    # Now empty
    r = client.get("/searches")
    assert r.json()["items"] == []


def test_delete_404_for_unknown_cache_key(client):
    r = client.delete("/searches/nope")
    assert r.status_code == 404


def test_post_save_validates_cadence_bounds(client, tmp_sqlite_url):
    import asyncio

    query = {"bedrooms_min": 1}
    asyncio.run(_seed_cache_row(tmp_sqlite_url, query))

    # cadence_minutes < 15 → 422 (Pydantic validation)
    r = client.post(
        "/searches",
        json={
            "query": {**query, "neighborhoods": [], "free_text_keywords": []},
            "label": "x",
            "cadence_minutes": 5,
        },
    )
    assert r.status_code == 422

    # cadence_minutes > 1440 → 422
    r = client.post(
        "/searches",
        json={
            "query": {**query, "neighborhoods": [], "free_text_keywords": []},
            "label": "x",
            "cadence_minutes": 99999,
        },
    )
    assert r.status_code == 422


def test_save_idempotent_relabel(client, tmp_sqlite_url):
    """Saving the same query twice updates the label without erroring."""
    import asyncio

    query = {"bedrooms_min": 1}
    asyncio.run(_seed_cache_row(tmp_sqlite_url, query))
    body = {
        "query": {**query, "neighborhoods": [], "free_text_keywords": []},
        "label": "first",
    }
    r1 = client.post("/searches", json=body)
    assert r1.status_code == 200

    body2 = {**body, "label": "second"}
    r2 = client.post("/searches", json=body2)
    assert r2.status_code == 200

    # Listing reflects the most recent label.
    items = client.get("/searches").json()["items"]
    assert len(items) == 1
    assert items[0]["label"] == "second"


def test_save_with_no_cadence_preserves_default(client, tmp_sqlite_url):
    import asyncio

    query = {"bedrooms_min": 1}
    asyncio.run(_seed_cache_row(tmp_sqlite_url, query))
    r = client.post(
        "/searches",
        json={
            "query": {**query, "neighborhoods": [], "free_text_keywords": []},
            "label": "x",
        },
    )
    assert r.status_code == 200
    # Default from migration is 60.
    assert r.json()["cadence_minutes"] == 60


def test_save_query_round_trips_neighborhoods(client, tmp_sqlite_url):
    import asyncio

    query = {"neighborhoods": ["Kitsilano", "West End"], "bedrooms_min": 2}
    asyncio.run(_seed_cache_row(tmp_sqlite_url, query))
    r = client.post(
        "/searches",
        json={
            "query": {**query, "free_text_keywords": []},
            "label": "two-hood",
        },
    )
    assert r.status_code == 200
    saved_query = r.json()["query"]
    assert saved_query["neighborhoods"] == ["Kitsilano", "West End"]
    assert saved_query["bedrooms_min"] == 2

    # Sanity: stored query_json round-trips through Pydantic
    items = client.get("/searches").json()["items"]
    assert items[0]["query"] == saved_query


# Quiet a lint about unused import — used inside the test fns.
_ = json
