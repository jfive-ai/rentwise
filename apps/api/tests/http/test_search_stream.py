"""POST /search/stream — NDJSON wire-format integration test (issue #113)."""

from __future__ import annotations

import concurrent.futures
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import HttpUrl

from alembic import command
from rentwise.adapters.base import AdapterCapabilities
from rentwise.models import AdapterHealth, NormalizedQuery, RawListing


class _StreamingFakeAdapter:
    name = "craigslist"
    base_url = "https://vancouver.craigslist.org"
    method = "rss"
    rate_limit_per_second = 1.0
    capabilities: ClassVar[AdapterCapabilities] = {"supported_filters": set()}

    async def search(self, query: NormalizedQuery) -> AsyncIterator[RawListing]:
        for i in range(2):
            yield RawListing(
                source="craigslist",
                source_url=HttpUrl(f"https://example.com/{i}"),
                source_listing_id=f"cl-{i}",
                title=f"$2000 / 1br - listing {i}",
                bedrooms=1.0,
                price_cad=2000,
                posted_at=datetime.now(UTC),
            )

    async def fetch_listing(self, listing_id: str):
        return None

    async def health_check(self) -> AdapterHealth:
        return AdapterHealth(name=self.name, status="ok")


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

    from rentwise.http.search import get_adapters

    app.dependency_overrides[get_adapters] = lambda: [_StreamingFakeAdapter()]

    with TestClient(app) as c:
        yield c


def test_stream_emits_ndjson_started_listings_complete(client):
    """Each line is a valid JSON object; event order is started → listings →
    adapter_done → complete; total matches the listing count."""
    with client.stream("POST", "/search/stream", json={"query": {}}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/x-ndjson")

        events: list[dict] = []
        for line in r.iter_lines():
            if not line:
                continue
            events.append(json.loads(line))

    assert events[0]["event"] == "started"
    assert events[-1]["event"] == "complete"

    listings = [e for e in events if e["event"] == "listing"]
    assert len(listings) == 2

    done = [e for e in events if e["event"] == "adapter_done"]
    assert len(done) == 1
    assert done[0]["adapter"] == "craigslist"
    assert done[0]["status"] == "ok"

    assert events[-1]["total"] == 2
    assert events[-1]["cache_status"] == "miss"
    assert "craigslist" in events[-1]["source_health"]


def test_stream_no_adapters_returns_empty_complete(client):
    """No adapters → started + complete only; total=0."""
    from rentwise.http.search import get_adapters

    client.app.dependency_overrides[get_adapters] = lambda: []

    with client.stream("POST", "/search/stream", json={"query": {}}) as r:
        events = [json.loads(line) for line in r.iter_lines() if line]

    types = [e["event"] for e in events]
    assert types[0] == "started"
    assert types[-1] == "complete"
    assert events[-1]["total"] == 0
