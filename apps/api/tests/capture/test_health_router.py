"""Tests for POST /capture/health — content scripts ping when selectors break."""

from __future__ import annotations

import asyncio
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


def _pair(client) -> str:
    return client.get(
        "/capture/pair", headers={"Origin": "http://localhost:8081"}
    ).json()["token"]


def test_health_requires_token(client):
    _pair(client)
    r = client.post(
        "/capture/health",
        json={
            "source": "rentals_ca",
            "schema_version": "2026-05-07",
            "status": "degraded",
            "reason": "card selector missing",
        },
    )
    assert r.status_code == 401


def test_health_records_degraded_status(client):
    from rentwise.storage.db import get_sessionmaker
    from rentwise.storage.repositories import SourceHealthRepo

    token = _pair(client)
    r = client.post(
        "/capture/health",
        json={
            "source": "rentals_ca",
            "schema_version": "2026-05-07",
            "status": "degraded",
            "reason": "card selector missing",
        },
        headers={"X-RentWise-Token": token},
    )
    assert r.status_code == 204

    async def _fetch():
        factory = get_sessionmaker()
        async with factory() as s:
            return await SourceHealthRepo(s).get("rentals_ca")

    health = asyncio.new_event_loop().run_until_complete(_fetch())
    assert health is not None
    assert health.status == "degraded"
    assert "card selector missing" in (health.last_error or "")
