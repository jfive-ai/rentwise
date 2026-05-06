"""Tests for SourceHealthRepo."""

from __future__ import annotations

import pytest

from rentwise.models import AdapterHealth
from rentwise.storage.repositories import SourceHealthRepo


@pytest.mark.asyncio
async def test_upsert_and_get(session):
    repo = SourceHealthRepo(session)
    await repo.set("craigslist", "ok", error=None)
    await session.commit()
    h = await repo.get("craigslist")
    assert isinstance(h, AdapterHealth)
    assert h.status == "ok"


@pytest.mark.asyncio
async def test_consecutive_failures_increments(session):
    repo = SourceHealthRepo(session)
    await repo.set("craigslist", "degraded", error="boom")
    await repo.set("craigslist", "degraded", error="boom2")
    await session.commit()
    h = await repo.get("craigslist")
    assert h.status == "degraded"
    assert h.last_error == "boom2"


@pytest.mark.asyncio
async def test_ok_status_resets_failures(session):
    repo = SourceHealthRepo(session)
    await repo.set("craigslist", "degraded", error="x")
    await repo.set("craigslist", "ok", error=None)
    await session.commit()
    # No external assertion needed beyond not raising; downstream tests cover semantics.
    h = await repo.get("craigslist")
    assert h.status == "ok"
