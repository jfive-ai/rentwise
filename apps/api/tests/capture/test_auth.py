"""Tests for verify_capture_token + verify_local_origin dependencies.

Exercised via TestClient against the /capture and /capture/pair routes that
Tasks 6 and 7 register.
"""

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


def _capture_body() -> dict:
    return {
        "source": "rentals_ca",
        "captured_at": "2026-05-07T12:00:00+00:00",
        "page_type": "search_results",
        "page_url": "https://rentals.ca/vancouver",
        "schema_version": "x",
        "listings": [],
    }


def test_verify_capture_token_rejects_when_unpaired(client):
    """If no pairing exists, every token is rejected with 401."""
    r = client.post(
        "/capture",
        headers={"X-RentWise-Token": "anything"},
        json=_capture_body(),
    )
    assert r.status_code == 401


def test_verify_capture_token_rejects_wrong_token(client):
    pair = client.get("/capture/pair", headers={"Origin": "http://localhost:8081"})
    assert pair.status_code == 200

    r = client.post(
        "/capture",
        headers={"X-RentWise-Token": "wrong-token"},
        json=_capture_body(),
    )
    assert r.status_code == 401


def test_verify_capture_token_accepts_correct(client):
    pair = client.get("/capture/pair", headers={"Origin": "http://localhost:8081"})
    token = pair.json()["token"]

    r = client.post(
        "/capture",
        headers={"X-RentWise-Token": token},
        json=_capture_body(),
    )
    assert r.status_code == 200


def test_verify_local_origin_rejects_external(client):
    r = client.get("/capture/pair", headers={"Origin": "https://evil.example.com"})
    assert r.status_code == 403


def test_verify_local_origin_accepts_localhost(client):
    r = client.get("/capture/pair", headers={"Origin": "http://localhost:8081"})
    assert r.status_code == 200


def test_verify_local_origin_accepts_127_0_0_1(client):
    r = client.get("/capture/pair", headers={"Origin": "http://127.0.0.1:3000"})
    assert r.status_code == 200


def test_verify_local_origin_rejects_missing_origin(client):
    r = client.get("/capture/pair")
    assert r.status_code == 403
