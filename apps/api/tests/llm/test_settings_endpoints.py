"""Endpoint tests for /settings/llm GET/PUT and /settings/llm/test."""

from __future__ import annotations

import pathlib
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from rentwise.main import app

_TEST_FERNET_KEY = "M2zZqQrAvFkkr_xWmaVjJqASfh-dhmL7yLQ2hM6oMmU="


@pytest.fixture(autouse=True)
def _isolate_db_and_keys(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Each test gets its own SQLite file + a fresh schema.

    Clearing the cache on teardown matters: without it, `get_engine`'s
    lru_cache holds a connection to the now-deleted tmp_path DB, which the
    next test file (e.g. test_translate_query_endpoint) inherits and fails
    on with a Fernet `InvalidToken` (DB rows were encrypted with the
    monkeypatched test key, but the live settings have reverted to the
    real key).
    """
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

    yield

    db_mod.get_engine.cache_clear()
    db_mod.get_sessionmaker.cache_clear()


@pytest.fixture
def http_client() -> TestClient:
    return TestClient(app)


def test_get_returns_404_when_unset(http_client: TestClient) -> None:
    resp = http_client.get("/settings/llm")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "no_llm_settings"


def test_put_creates_settings_then_get_returns_masked(http_client: TestClient) -> None:
    body = {
        "primary_model": "openrouter/qwen/qwen3-next-80b-a3b-instruct:free",
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
            "model": "openrouter/qwen/qwen3-next-80b-a3b-instruct:free",
            "choices": [type("C", (), {"message": type("M", (), {"content": "ok"})()})()],
        },
    )()
    mock = AsyncMock(return_value=fake_response)
    monkeypatch.setattr("rentwise.main.acompletion", mock)

    body = {
        "primary_model": "openrouter/qwen/qwen3-next-80b-a3b-instruct:free",
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


def test_test_connection_uses_max_tokens_large_enough_for_reasoning_models(
    http_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression for #59: a 1-token ping fails on gpt-5.x / o-series because
    reasoning consumes the budget before any visible output. The endpoint
    must send a max_tokens generous enough for current reasoning models."""
    fake_response = type(
        "R",
        (),
        {
            "model": "openai/gpt-5.5",
            "choices": [type("C", (), {"message": type("M", (), {"content": "ok"})()})()],
        },
    )()
    mock = AsyncMock(return_value=fake_response)
    monkeypatch.setattr("rentwise.main.acompletion", mock)

    resp = http_client.post(
        "/settings/llm/test",
        json={"primary_model": "openai/gpt-5.5", "primary_api_key": "sk-test"},
    )
    assert resp.status_code == 200, resp.text

    assert mock.await_count == 1
    kwargs = mock.await_args.kwargs
    # 64 is the loose lower bound: a future "let's make it cheaper" change
    # that pushes max_tokens below this trips the regression. Current value
    # is 256.
    assert kwargs["max_tokens"] >= 64, (
        f"max_tokens={kwargs['max_tokens']} is too small for reasoning models"
    )


def test_test_connection_failure_returns_ok_false(
    http_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock = AsyncMock(side_effect=RuntimeError("provider unreachable"))
    monkeypatch.setattr("rentwise.main.acompletion", mock)

    body = {
        "primary_model": "openrouter/qwen/qwen3-next-80b-a3b-instruct:free",
        "primary_api_key": "sk-or-v1-test",
    }
    resp = http_client.post("/settings/llm/test", json=body)
    assert resp.status_code == 200
    out = resp.json()
    assert out["ok"] is False
    assert "provider unreachable" in (out["error"] or "")


def test_test_connection_falls_back_to_saved_key_when_body_omits_it(
    http_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Returning user revisits Settings, sees the masked key, and clicks
    Test connection without clicking Replace. The frontend sends
    primary_api_key=null. The endpoint must re-use the persisted key —
    otherwise Test always fails with "api_key must be set" until you
    re-paste the key, which is the bug we're fixing."""
    fake_response = type(
        "R",
        (),
        {
            "model": "openai/gpt-5-nano",
            "choices": [type("C", (), {"message": type("M", (), {"content": "ok"})()})()],
        },
    )()
    mock = AsyncMock(return_value=fake_response)
    monkeypatch.setattr("rentwise.main.acompletion", mock)

    # Seed via PUT (mirrors the wizard saving)
    put = http_client.put(
        "/settings/llm",
        json={
            "primary_model": "openai/gpt-5-nano",
            "primary_api_key": "sk-real-saved-key",
        },
    )
    assert put.status_code == 200

    # Now Test connection with no key in the body (the masked key never
    # round-trips)
    resp = http_client.post(
        "/settings/llm/test",
        json={"primary_model": "openai/gpt-5-nano"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True

    # Crucially, the saved key was passed to LiteLLM
    assert mock.await_args.kwargs["api_key"] == "sk-real-saved-key"


def test_test_connection_does_not_use_saved_key_for_a_different_model(
    http_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the user picks a different model than what's saved, the saved
    key shouldn't be silently sent — it likely belongs to a different
    provider (e.g. switching from OpenAI to Anthropic) and would 401."""
    mock = AsyncMock(return_value=type("R", (), {"model": "x", "choices": []})())
    monkeypatch.setattr("rentwise.main.acompletion", mock)

    http_client.put(
        "/settings/llm",
        json={
            "primary_model": "openai/gpt-5-nano",
            "primary_api_key": "sk-openai",
        },
    )

    http_client.post(
        "/settings/llm/test",
        json={"primary_model": "anthropic/claude-sonnet-4"},
    )
    assert "api_key" not in mock.await_args.kwargs
