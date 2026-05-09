"""Tests for /map/overlays/* (Phase 7 PR-B)."""

from __future__ import annotations

import concurrent.futures
import json
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


def test_catchments_returns_feature_collection(client):
    r = client.get("/map/overlays/catchments")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/geo+json")
    assert "max-age=86400" in r.headers.get("cache-control", "")
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert isinstance(body["features"], list)
    assert len(body["features"]) > 0


def test_catchments_503_when_file_missing(monkeypatch, client):
    """If the data file is renamed / removed, the endpoint fails closed."""
    from pathlib import Path as _Path

    from rentwise.http import map_overlays

    monkeypatch.setattr(map_overlays, "DEFAULT_GEOJSON", _Path("/tmp/rentwise-missing.geojson"))
    r = client.get("/map/overlays/catchments")
    assert r.status_code == 503
    assert r.json()["detail"] == "catchments_unavailable"


def test_skytrain_stops_returns_only_skytrain(client):
    r = client.get("/map/overlays/skytrain-stops")
    assert r.status_code == 200
    body = r.json()
    assert "stops" in body
    assert all("skytrain" in s.get("route_types", []) for s in body["stops"]), (
        "expected only skytrain-tagged stops"
    )
    # The synthetic fixture has a dozen skytrain stops + a couple bus stops.
    assert len(body["stops"]) >= 1
    # Verify the bus-only stops were filtered out.
    raw = json.loads(
        Path(
            "rentwise/enrichment/data/translink_stops.json",
        ).read_text(encoding="utf-8")
    )
    bus_count = sum(
        1
        for s in raw["stops"]
        if "bus" in s.get("route_types", []) and "skytrain" not in s.get("route_types", [])
    )
    if bus_count > 0:
        assert len(body["stops"]) < len(raw["stops"])


def test_skytrain_stops_503_when_file_missing(monkeypatch, client):
    from pathlib import Path as _Path

    from rentwise.http import map_overlays

    monkeypatch.setattr(map_overlays, "DEFAULT_STOPS_JSON", _Path("/tmp/rentwise-missing.json"))
    r = client.get("/map/overlays/skytrain-stops")
    assert r.status_code == 503
    assert r.json()["detail"] == "stops_unavailable"


def test_neighborhoods_returns_feature_collection(client):
    """The 22 City of Vancouver local-area polygons (#92)."""
    r = client.get("/map/overlays/neighborhoods")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/geo+json")
    assert "max-age=86400" in r.headers.get("cache-control", "")
    body = r.json()
    assert body["type"] == "FeatureCollection"
    names = {f["properties"]["name"] for f in body["features"]}
    assert "Dunbar-Southlands" in names
    assert "West Point Grey" in names
    assert "Kitsilano" in names
    assert len(body["features"]) == 22


def test_neighborhoods_503_when_file_missing(monkeypatch, client):
    from pathlib import Path as _Path

    from rentwise.http import map_overlays

    monkeypatch.setattr(
        map_overlays,
        "DEFAULT_NEIGHBORHOODS_GEOJSON",
        _Path("/tmp/rentwise-missing-neighborhoods.geojson"),
    )
    r = client.get("/map/overlays/neighborhoods")
    assert r.status_code == 503
    assert r.json()["detail"] == "neighborhoods_unavailable"
