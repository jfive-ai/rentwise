"""HTTP layer for web push subscriptions (Phase 5 PR-C)."""

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
    settings.rentwise_web_push_enabled = True
    settings.rentwise_vapid_public_key = "PUBLIC_BASE64URL"
    settings.rentwise_vapid_private_key = "PRIVATE_BASE64URL"

    from rentwise.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c

    # Restore module-level toggles for downstream tests.
    settings.rentwise_web_push_enabled = False
    settings.rentwise_vapid_public_key = None
    settings.rentwise_vapid_private_key = None


def test_public_key_returns_503_when_disabled(monkeypatch, tmp_sqlite_url):
    """Without enable + key set, endpoints fail closed (no panic on first deploy)."""
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
    settings.rentwise_web_push_enabled = False
    settings.rentwise_vapid_public_key = None

    from rentwise.main import create_app

    app = create_app()
    with TestClient(app) as c:
        r = c.get("/notifications/web-push/public-key")
        assert r.status_code == 503


def test_public_key_returns_configured_value(client):
    r = client.get("/notifications/web-push/public-key")
    assert r.status_code == 200
    assert r.json() == {"public_key": "PUBLIC_BASE64URL"}


def test_subscribe_then_unsubscribe(client):
    body = {
        "endpoint": "https://push.example/abc",
        "keys": {"p256dh": "p1", "auth": "a1"},
        "alert_email": "me@example.com",
        "label": "MacBook Chrome",
    }
    r = client.post("/notifications/web-push/subscribe", json=body)
    assert r.status_code == 200, r.text
    sub = r.json()
    assert sub["endpoint"] == body["endpoint"]
    assert sub["alert_email"] == "me@example.com"
    assert isinstance(sub["id"], int)

    r2 = client.delete(f"/notifications/web-push/subscribe/{sub['id']}")
    assert r2.status_code == 204


def test_subscribe_idempotent_on_same_endpoint(client):
    """Re-subscribing the same browser updates in place, no duplicate row."""
    body = {
        "endpoint": "https://push.example/abc",
        "keys": {"p256dh": "p1", "auth": "a1"},
        "alert_email": "me@example.com",
        "label": "Original",
    }
    r1 = client.post("/notifications/web-push/subscribe", json=body)
    assert r1.status_code == 200
    body["label"] = "Renamed"
    r2 = client.post("/notifications/web-push/subscribe", json=body)
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]
    assert r2.json()["label"] == "Renamed"


def test_unsubscribe_404(client):
    r = client.delete("/notifications/web-push/subscribe/99999")
    assert r.status_code == 404


def test_subscribe_validates_payload(client):
    # Missing keys.auth
    bad = {
        "endpoint": "https://push.example/abc",
        "keys": {"p256dh": "p1"},
    }
    r = client.post("/notifications/web-push/subscribe", json=bad)
    assert r.status_code == 422

    # Empty endpoint
    bad2 = {
        "endpoint": "",
        "keys": {"p256dh": "p1", "auth": "a1"},
    }
    r2 = client.post("/notifications/web-push/subscribe", json=bad2)
    assert r2.status_code == 422
