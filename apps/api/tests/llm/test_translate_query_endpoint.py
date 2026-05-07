"""Tests for the /translate-query FastAPI endpoint."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from rentwise.llm import LLMTransportError, TranslateQueryResult
from rentwise.main import app
from rentwise.models import NormalizedQuery, PetPolicy


@pytest.fixture
def client_under_test(monkeypatch: pytest.MonkeyPatch):
    return TestClient(app)


def _stub_client(
    monkeypatch: pytest.MonkeyPatch, *, return_value: Any = None, side_effect: Any = None
) -> AsyncMock:
    """Replace LLMClient.translate_query with a mock for the test."""
    mock = AsyncMock()
    if side_effect is not None:
        mock.side_effect = side_effect
    else:
        mock.return_value = return_value
    monkeypatch.setattr("rentwise.main.LLMClient.translate_query", mock)
    return mock


def test_translate_query_happy_path_en(monkeypatch, client_under_test) -> None:
    _stub_client(
        monkeypatch,
        return_value=TranslateQueryResult(
            query=NormalizedQuery(
                bedrooms_min=2, price_max=3000, neighborhoods=["Kitsilano"], pets=PetPolicy.OK
            ),
            unsupported_filters=[],
            lang_detected="en",
            model_used="openrouter/qwen/qwen-2.5-72b-instruct:free",
        ),
    )
    resp = client_under_test.post("/translate-query", json={"text": "2br Kits under 3000 pet ok"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["lang_detected"] == "en"
    assert body["model_used"] == "openrouter/qwen/qwen-2.5-72b-instruct:free"
    assert body["query"]["bedrooms_min"] == 2
    assert body["query"]["price_max"] == 3000
    assert body["query"]["neighborhoods"] == ["Kitsilano"]
    assert body["query"]["pets"] == "ok"


def test_translate_query_happy_path_ko(monkeypatch, client_under_test) -> None:
    _stub_client(
        monkeypatch,
        return_value=TranslateQueryResult(
            query=NormalizedQuery(bedrooms_min=2, price_max=3000, neighborhoods=["Kitsilano"]),
            unsupported_filters=[],
            lang_detected="ko",
            model_used="openrouter/qwen/qwen-2.5-72b-instruct:free",
        ),
    )
    resp = client_under_test.post("/translate-query", json={"text": "키츠 2베드 3000불 이하"})
    assert resp.status_code == 200
    assert resp.json()["lang_detected"] == "ko"


def test_translate_query_rejects_empty_input(client_under_test) -> None:
    resp = client_under_test.post("/translate-query", json={"text": ""})
    assert resp.status_code == 422


def test_translate_query_rejects_whitespace_only(client_under_test) -> None:
    resp = client_under_test.post("/translate-query", json={"text": "   \n\t  "})
    assert resp.status_code == 422


def test_translate_query_rejects_too_long(client_under_test) -> None:
    resp = client_under_test.post("/translate-query", json={"text": "x" * 1001})
    assert resp.status_code == 422


def test_translate_query_returns_502_on_llm_transport_error(monkeypatch, client_under_test) -> None:
    _stub_client(monkeypatch, side_effect=LLMTransportError("provider down"))
    resp = client_under_test.post("/translate-query", json={"text": "1br anywhere"})
    assert resp.status_code == 502
    body = resp.json()
    assert body["detail"]["error"] == "llm_transport_error"
    assert "provider down" in body["detail"]["message"]
