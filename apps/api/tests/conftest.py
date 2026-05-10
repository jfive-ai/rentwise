"""Shared pytest fixtures for the rentwise test suite."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command


@pytest.fixture
def tmp_sqlite_url(tmp_path: Path) -> str:
    """File-based SQLite (in tmp dir). Required because Alembic needs a real
    file URL to attach via async_engine_from_config; pure :memory: doesn't
    persist between connections.
    """
    return f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
async def migrated_engine(tmp_sqlite_url: str):
    """Apply Alembic migrations to a temp DB, yield an async engine over it.

    Alembic's command.upgrade() is synchronous and its env.py calls
    asyncio.run() internally.  That fails if an event loop is already running
    (pytest-asyncio runs tests inside one).  We work around by off-loading
    the upgrade to a thread — threads have no running event loop, so
    asyncio.run() works fine there.
    """
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", tmp_sqlite_url)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: command.upgrade(cfg, "head"))

    engine = create_async_engine(tmp_sqlite_url, future=True)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(migrated_engine) -> AsyncSession:
    factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest.fixture(autouse=True)
async def _reset_playwright_pool():
    """Tear down the process-wide Playwright pool between tests.

    Without this, mock state from one test (fake browsers, fake
    contexts) leaks into the next via the singleton, and tests that
    patch ``async_playwright`` see stale objects.
    """
    yield
    from rentwise.adapters.playwright_pool import PlaywrightPool

    await PlaywrightPool.reset()
