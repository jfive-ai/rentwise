"""POST /searches/{cache_key}/run-now — milestone integration test.

Wires:
- Real /searches save → backed by real SearchRepo + DB
- get_alert_runner overridden with a fake aggregator + recording
  notifier so no SMTP is touched.

The first call sends an email and records the dedup row; the second
call sends zero. That's the Phase 5 milestone proven through HTTP.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import HttpUrl

from alembic import command
from rentwise.models import (
    NormalizedListing,
    SchoolCatchments,
    SearchRequest,
    SearchResponse,
)
from rentwise.notifications.email import EmailAlert
from rentwise.notifications.runner import AlertRunner, RunnerConfig


def _listing(idx: int) -> NormalizedListing:
    nid = UUID(int=idx)
    now = datetime.now(UTC)
    return NormalizedListing(
        id=nid,
        canonical_id=nid,
        source="craigslist",
        source_url=HttpUrl(f"https://example.com/listing/{idx}"),
        source_listing_id=str(idx),
        title=f"Listing {idx}",
        address="1234 W 4th Ave",
        address_normalized=None,
        lat=None,
        lon=None,
        bedrooms=2.0,
        bathrooms=None,
        price_cad=2800,
        pets_allowed=None,
        furnished=None,
        available_date=None,
        posted_at=now,
        last_seen_at=now,
        photos=[],
        description_snippet=None,
        school_catchments=SchoolCatchments(),
        raw_metadata={},
    )


class FakeAggregator:
    def __init__(self, listings: list[NormalizedListing]) -> None:
        self._listings = listings
        self.calls = 0

    async def search(self, req: SearchRequest) -> SearchResponse:
        self.calls += 1
        return SearchResponse(
            listings=list(self._listings),
            total=len(self._listings),
            cache_status="miss",
            unsupported_filters=[],
            source_health={},
        )


class RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[EmailAlert] = []

    async def send_alert(self, alert: EmailAlert) -> None:
        self.sent.append(alert)


@pytest.fixture
def runtime(monkeypatch, tmp_sqlite_url):
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

    from rentwise.http.searches import get_alert_runner
    from rentwise.main import create_app

    app = create_app()

    fake_agg = FakeAggregator([_listing(1), _listing(2)])
    notifier = RecordingNotifier()

    def runner_dep(session):
        from rentwise.storage.repositories import AlertLogRepo

        return AlertRunner(
            aggregator=fake_agg,
            notifier=notifier,
            alert_log=AlertLogRepo(session),
            config=RunnerConfig(app_base_url="https://app.example"),
        )

    # Wrap with the FastAPI Depends signature so dependency_overrides can
    # call it directly.
    from fastapi import Depends

    from rentwise.storage.db import session_dep

    async def override(session=Depends(session_dep)):
        return runner_dep(session)

    app.dependency_overrides[get_alert_runner] = override

    with TestClient(app) as client:
        yield client, fake_agg, notifier


def _seed_saved(tmp_sqlite_url: str, alert_email: str | None = "me@example.com") -> str:
    """Drop in a saved search via the actual repo."""

    async def go() -> str:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from rentwise.aggregator.freshness import cache_key as compute_key
        from rentwise.models import NormalizedQuery
        from rentwise.storage.repositories import CachedSearch, SearchRepo

        q = NormalizedQuery(bedrooms_min=2)
        key = compute_key(q)
        engine = create_async_engine(tmp_sqlite_url)
        sessmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessmaker() as session:
            repo = SearchRepo(session)
            await repo.upsert(
                CachedSearch(
                    cache_key=key,
                    query_json=q.model_dump_json(),
                    listing_ids=[],
                    total_count=0,
                    is_saved=False,
                )
            )
            await repo.save(key, label="2br", alert_enabled=True, alert_email=alert_email)
            await session.commit()
        await engine.dispose()
        return key

    return asyncio.run(go())


def test_run_now_404_for_unknown_key(runtime):
    client, _agg, _notifier = runtime
    r = client.post("/searches/nope/run-now")
    assert r.status_code == 404


def test_run_now_first_call_sends_email_second_does_not(runtime, tmp_sqlite_url):
    """The Phase 5 milestone, proven via HTTP."""
    client, _agg, notifier = runtime
    key = _seed_saved(tmp_sqlite_url)

    r1 = client.post(f"/searches/{key}/run-now")
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1["cache_key"] == key
    assert body1["new_listings"] == 2
    assert body1["sent"] == 2
    assert body1["skipped"] is False
    assert len(notifier.sent) == 1

    r2 = client.post(f"/searches/{key}/run-now")
    body2 = r2.json()
    assert body2["new_listings"] == 0
    assert body2["sent"] == 0
    assert len(notifier.sent) == 1  # no second email


def test_run_now_skipped_when_alert_disabled(runtime, tmp_sqlite_url):
    client, _agg, notifier = runtime
    key = _seed_saved(tmp_sqlite_url, alert_email=None)

    r = client.post(f"/searches/{key}/run-now")
    body = r.json()
    assert body["skipped"] is True
    assert body["sent"] == 0
    assert notifier.sent == []


# Quiet linter about unused import — used inside _seed_saved closure.
_ = json
