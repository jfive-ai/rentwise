"""Tests for ``rentwise.storage.migrate.run_migrations``."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from rentwise.storage.migrate import run_migrations


@pytest.fixture
def fresh_db(tmp_path: Path) -> tuple[Path, str]:
    """A path to a not-yet-created sqlite file, and its async URL."""
    db_path = tmp_path / "fresh.db"
    return db_path, f"sqlite+aiosqlite:///{db_path}"


@pytest.mark.asyncio
async def test_run_migrations_creates_expected_tables(fresh_db: tuple[Path, str]) -> None:
    db_path, url = fresh_db
    assert not db_path.exists()

    await run_migrations(database_url=url)

    eng = create_engine(f"sqlite:///{db_path}")
    try:
        tables = set(inspect(eng).get_table_names())
    finally:
        eng.dispose()

    # Spot-check a representative slice across the migration history.
    # alembic_version proves the upgrade ran; llm_settings is the table that
    # motivated this fix; listings is the core schema from 0001.
    for name in ("alembic_version", "llm_settings", "listings"):
        assert name in tables, f"missing table {name!r} after migrate; got {sorted(tables)}"


@pytest.mark.asyncio
async def test_run_migrations_is_idempotent(fresh_db: tuple[Path, str]) -> None:
    _, url = fresh_db
    await run_migrations(database_url=url)
    # Second call must not raise — Alembic should treat an at-head DB as a no-op.
    await run_migrations(database_url=url)
