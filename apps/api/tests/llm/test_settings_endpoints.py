"""Endpoint tests for /settings/llm GET/PUT and /settings/llm/test."""

from __future__ import annotations

import pathlib
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from rentwise.main import app

_TEST_FERNET_KEY = "M2zZqQrAvFkkr_xWmaVjJqASfh-dhmL7yLQ2hM6oMmU="


@pytest.fixture(autouse=True)
def _isolate_db_and_keys(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test gets its own SQLite file + a fresh schema."""
    from alembic.config import Config

    from alembic import command
    from rentwise.storage import db as db_mod

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setattr("rentwise.settings.settings.database_url", db_url)
    monkeypatch.setattr(
        "rentwise.llm.settings_crypto.settings.rentwise_settings_encryption_key",
        _TEST_FERNET_KEY,
    )
    db_mod.get_engine.cache_clear()
    db_mod.get_sessionmaker.cache_clear()

    cfg = Config(str(pathlib.Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")


@pytest.fixture
def http_client() -> TestClient:
    return TestClient(app)


def test_get_returns_404_when_unset(http_client: TestClient) -> None:
    resp = http_client.get("/settings/llm")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "no_llm_settings"


def test_put_creates_settings_then_get_returns_masked(http_client: TestClient) -> None:
    body = {
        "primary_model": "openrouter/qwen/qwen-2.5-72b-instruct:free",
        "primary_api_key": "sk-or-v1-aabbccddeeff",
        "timeout_seconds": 20,
    }
    put = http_client.put("/settings/llm", json=body)
    assert put.status_code == 200, put.text
    payload = put.json()
    assert payload["primary_model"] == body["primary_model"]
    assert payload["primary_api_key_masked"] == "sk-or-...eeff"
    assert "primary_api_key" not in payload  # secret never echoed back

    got = http_client.get("/settings/llm").json()
    assert got["primary_model"] == body["primary_model"]
    assert got["primary_api_key_masked"] == "sk-or-...eeff"
    assert got["timeout_seconds"] == 20


def test_put_validates_required_fields(http_client: TestClient) -> None:
    resp = http_client.put("/settings/llm", json={})
    assert resp.status_code == 422


def test_put_clear_primary_key_via_flag(http_client: TestClient) -> None:
    # Seed
    http_client.put(
        "/settings/llm",
        json={"primary_model": "m", "primary_api_key": "sk-test"},
    )
    # Clear
    resp = http_client.put(
        "/settings/llm",
        json={"primary_model": "m", "primary_api_key_clear": True},
    )
    assert resp.status_code == 200
    assert resp.json()["primary_api_key_masked"] is None


def test_test_connection_success_does_not_persist(
    http_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_response = type(
        "R",
        (),
        {
            "model": "openrouter/qwen/qwen-2.5-72b-instruct:free",
            "choices": [type("C", (), {"message": type("M", (), {"content": "ok"})()})()],
        },
    )()
    mock = AsyncMock(return_value=fake_response)
    monkeypatch.setattr("rentwise.main.acompletion", mock)

    body = {
        "primary_model": "openrouter/qwen/qwen-2.5-72b-instruct:free",
        "primary_api_key": "sk-or-v1-test",
        "timeout_seconds": 5,
    }
    resp = http_client.post("/settings/llm/test", json=body)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["ok"] is True
    assert out["error"] is None
    assert out["latency_ms"] >= 0
    assert out["model_used"] == body["primary_model"]
    # And no settings persisted
    get = http_client.get("/settings/llm")
    assert get.status_code == 404


def test_test_connection_failure_returns_ok_false(
    http_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock = AsyncMock(side_effect=RuntimeError("provider unreachable"))
    monkeypatch.setattr("rentwise.main.acompletion", mock)

    body = {
        "primary_model": "openrouter/qwen/qwen-2.5-72b-instruct:free",
        "primary_api_key": "sk-or-v1-test",
    }
    resp = http_client.post("/settings/llm/test", json=body)
    assert resp.status_code == 200
    out = resp.json()
    assert out["ok"] is False
    assert "provider unreachable" in (out["error"] or "")
