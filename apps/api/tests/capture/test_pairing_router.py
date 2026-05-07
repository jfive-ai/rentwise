"""Tests for /capture/pair + /capture/pair/rotate."""

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


def test_pair_get_creates_token_on_first_call(client):
    r = client.get("/capture/pair", headers={"Origin": "http://localhost:8081"})
    assert r.status_code == 200
    body = r.json()
    assert "token" in body and len(body["token"]) >= 32
    assert body["server_url"].startswith("http://127.0.0.1")


def test_pair_get_returns_same_token_on_repeat(client):
    a = client.get("/capture/pair", headers={"Origin": "http://localhost:8081"}).json()
    b = client.get("/capture/pair", headers={"Origin": "http://localhost:8081"}).json()
    assert a["token"] == b["token"]


def test_pair_rotate_changes_token(client):
    a = client.get("/capture/pair", headers={"Origin": "http://localhost:8081"}).json()
    rot = client.post(
        "/capture/pair/rotate", headers={"Origin": "http://localhost:8081"}
    )
    assert rot.status_code == 200
    b = client.get("/capture/pair", headers={"Origin": "http://localhost:8081"}).json()
    assert a["token"] != b["token"]


def test_pair_blocks_external_origin(client):
    r = client.get("/capture/pair", headers={"Origin": "https://evil.example.com"})
    assert r.status_code == 403
