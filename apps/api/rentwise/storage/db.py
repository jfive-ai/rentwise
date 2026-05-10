"""Async SQLAlchemy engine + session factory.

A single engine per process (lazy-init); a session factory that yields
short-lived sessions. Routes use `Depends(session_dep)` to obtain one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from rentwise.settings import settings


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    engine = create_async_engine(
        settings.database_url,
        future=True,
        echo=False,
        pool_pre_ping=True,
    )
    # SQLite ships with single-writer file locking and a 0 ms busy
    # timeout, so any two concurrent /search requests immediately raise
    # `OperationalError: database is locked`. That OperationalError
    # poisons the SQLAlchemy session, the aggregator's per-adapter
    # except block then writes health on the same session and gets
    # PendingRollbackError, and the wrapper at http/search.py turns
    # everything into a generic HTTP 503. Server-friendly PRAGMAs (#109):
    #   - WAL: concurrent readers + a single writer, persistent on file.
    #   - busy_timeout=15000: writers wait up to 15 s for the lock. The
    #     aggregator commits per-adapter so the actual lock window is
    #     milliseconds, but a slow adapter inside one request can still
    #     hold it for a few seconds during enrichment writes; 15 s is
    #     comfortably above that without making genuinely-stuck
    #     requests painful for the user. Bumped from 5 s in the #109
    #     follow-up.
    #   - synchronous=NORMAL: safe with WAL, materially faster than FULL.
    #   - foreign_keys=ON: SQLite defaults this off; we want it on.
    # The listener is a no-op for non-SQLite URLs (Postgres is the
    # multi-user upgrade path documented in docs/architecture.md).
    if settings.database_url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=15000")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()

    return engine


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def session_dep() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an AsyncSession."""
    factory = get_sessionmaker()
    async with factory() as session:
        yield session
