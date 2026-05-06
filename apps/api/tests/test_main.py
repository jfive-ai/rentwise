"""Smoke tests for Phase 0 endpoints."""

from fastapi.testclient import TestClient

from rentwise.main import app

client = TestClient(app)


def test_root() -> None:
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "RentWise"
    assert body["status"] == "ok"


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_llm_health_reports_config() -> None:
    r = client.get("/health/llm")
    assert r.status_code == 200
    body = r.json()
    assert "configured" in body
    assert "primary_model" in body


def test_search_stub_returns_empty_results() -> None:
    r = client.post("/search", json={})
    assert r.status_code == 200
    assert r.json()["results"] == []


def test_translate_query_stub() -> None:
    r = client.post("/translate-query", json={"text": "2br Kits under 3000"})
    assert r.status_code == 200
    body = r.json()
    assert body["input"] == "2br Kits under 3000"
    assert "parsed" in body
