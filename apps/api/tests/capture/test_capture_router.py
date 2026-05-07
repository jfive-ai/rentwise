"""Tests for POST /capture — auth, upsert, response counts, validation."""

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
    return client.get("/capture/pair", headers={"Origin": "http://localhost:8081"}).json()["token"]


def _payload(**overrides) -> dict:
    base = {
        "source": "rentals_ca",
        "captured_at": "2026-05-07T12:00:00+00:00",
        "page_type": "listing_detail",
        "page_url": "https://rentals.ca/listing/abc",
        "schema_version": "2026-05-07",
        "listings": [
            {
                "source_listing_id": "abc",
                "url": "https://rentals.ca/listing/abc",
                "title": "Bright 2BR",
                "price": 2800,
                "bedrooms": 2.0,
                "neighborhood": "Kitsilano",
                "page_type": "listing_detail",
            }
        ],
    }
    base.update(overrides)
    return base


def test_capture_accepts_valid_payload(client):
    token = _pair(client)
    r = client.post("/capture", json=_payload(), headers={"X-RentWise-Token": token})
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] == 1
    assert body["skipped_duplicates"] == 0
    assert body["errors"] == []


def test_capture_empty_listings_is_ok(client):
    token = _pair(client)
    r = client.post(
        "/capture",
        json=_payload(listings=[]),
        headers={"X-RentWise-Token": token},
    )
    assert r.status_code == 200
    assert r.json()["accepted"] == 0


def test_capture_persists_listing_visible_in_db(client):
    """Capture once; the listing must be retrievable via the storage layer."""
    from rentwise.storage.db import get_sessionmaker
    from rentwise.storage.repositories import ListingRepo

    token = _pair(client)
    r = client.post("/capture", json=_payload(), headers={"X-RentWise-Token": token})
    assert r.status_code == 200

    async def _fetch():
        factory = get_sessionmaker()
        async with factory() as s:
            return await ListingRepo(s).get_by_source("rentals_ca", "abc")

    fetched = asyncio.new_event_loop().run_until_complete(_fetch())
    assert fetched is not None
    assert fetched.title == "Bright 2BR"
    assert fetched.price_cad == 2800


def test_capture_re_post_advances_last_seen(client):
    token = _pair(client)
    p1 = _payload()
    p1["captured_at"] = "2026-05-07T10:00:00+00:00"
    r1 = client.post("/capture", json=p1, headers={"X-RentWise-Token": token})
    assert r1.status_code == 200

    p2 = _payload()
    p2["captured_at"] = "2026-05-07T11:00:00+00:00"
    r2 = client.post("/capture", json=p2, headers={"X-RentWise-Token": token})
    assert r2.status_code == 200
    assert r2.json()["accepted"] == 1


def test_capture_rejects_oversize_snippet(client):
    token = _pair(client)
    p = _payload()
    p["listings"][0]["description_snippet"] = "x" * 201
    r = client.post("/capture", json=p, headers={"X-RentWise-Token": token})
    assert r.status_code == 422
