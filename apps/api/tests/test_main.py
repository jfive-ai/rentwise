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


def test_search_returns_search_response_shape() -> None:
    # Phase 1: /search now returns a SearchResponse (not the Phase 0 stub).
    # A bare empty POST body is invalid (missing required `query` key) → 422.
    r = client.post("/search", json={})
    assert r.status_code == 422

    # With a minimal valid payload the real router must return the new shape.
    r = client.post("/search", json={"query": {}})
    assert r.status_code in (200, 503)  # 503 if DB not migrated in this context
    if r.status_code == 200:
        body = r.json()
        assert "total" in body
        assert "cache_status" in body
        assert "unsupported_filters" in body
        assert "source_health" in body
