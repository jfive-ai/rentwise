"""Regression tests for the SQLite PRAGMAs configured by `get_engine`.

Without these PRAGMAs, two concurrent /search requests immediately
race on SQLite's file-level write lock, the resulting
``OperationalError: database is locked`` poisons the SQLAlchemy
session, and the aggregator's failure handling escalates the whole
request to HTTP 503 (#109).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import text

from rentwise.settings import settings
from rentwise.storage import db


@pytest.fixture
def isolated_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Build the production engine against a throwaway DB file.

    ``get_engine`` is ``lru_cache``'d on a process-wide singleton
    (intentional — we want one engine per worker), so the test must
    monkeypatch ``settings.database_url`` and clear the cache around
    the test.
    """
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'pragmas.db'}"
    monkeypatch.setattr(settings, "database_url", db_url)
    db.get_engine.cache_clear()
    db.get_sessionmaker.cache_clear()
    yield db.get_engine()
    db.get_engine.cache_clear()
    db.get_sessionmaker.cache_clear()


@pytest.mark.asyncio
async def test_sqlite_pragmas_are_applied(isolated_engine):
    """journal_mode=WAL and busy_timeout>=5000 must be set on every connection."""
    async with isolated_engine.connect() as conn:
        journal_mode = (await conn.execute(text("PRAGMA journal_mode"))).scalar()
        busy_timeout = (await conn.execute(text("PRAGMA busy_timeout"))).scalar()
        synchronous = (await conn.execute(text("PRAGMA synchronous"))).scalar()
        foreign_keys = (await conn.execute(text("PRAGMA foreign_keys"))).scalar()

    assert str(journal_mode).lower() == "wal", (
        f"expected WAL journal mode for #109 fix, got {journal_mode!r}"
    )
    assert int(busy_timeout) >= 5000, (
        f"expected busy_timeout >= 5000ms for #109 fix, got {busy_timeout!r}"
    )
    # synchronous=NORMAL (1) is required to keep WAL fast and is still
    # crash-safe for our durability needs; FULL (2) would be wasteful.
    assert int(synchronous) == 1, f"expected synchronous=NORMAL (1), got {synchronous!r}"
    assert int(foreign_keys) == 1, f"expected foreign_keys=ON, got {foreign_keys!r}"


@pytest.mark.asyncio
async def test_concurrent_writes_do_not_immediately_lock(isolated_engine):
    """Two writers on separate connections must not raise database-is-locked.

    This is the actual symptom from #109: with the default
    busy_timeout=0, the second writer fails instantly. With
    busy_timeout=5000 (and WAL), the second one waits for the first to
    finish and both succeed.
    """
    async with isolated_engine.begin() as setup:
        await setup.execute(text("CREATE TABLE t (k INTEGER PRIMARY KEY, v TEXT)"))

    async def writer(value: str) -> None:
        async with isolated_engine.begin() as conn:
            await conn.execute(text("INSERT INTO t (v) VALUES (:v)"), {"v": value})
            # Hold the write lock briefly so the other writer is forced
            # to wait. Without busy_timeout this would trigger
            # OperationalError on the loser; with busy_timeout it
            # blocks for up to 5 s and then succeeds.
            await asyncio.sleep(0.05)

    await asyncio.gather(writer("a"), writer("b"))

    async with isolated_engine.connect() as conn:
        rows = (await conn.execute(text("SELECT v FROM t ORDER BY v"))).scalars().all()
    assert rows == ["a", "b"]
