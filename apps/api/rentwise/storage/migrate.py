"""Apply Alembic migrations programmatically.

Used by ``main.create_app()`` at startup so a freshly cloned checkout (or one
that just pulled new migrations) has a usable DB without anyone remembering
to run ``alembic upgrade head`` by hand. Idempotent — running on an
already-up-to-date DB is a no-op.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
from alembic.config import Config

from alembic import command

log = structlog.get_logger(__name__)

# apps/api/rentwise/storage/migrate.py → apps/api/alembic.ini
_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _upgrade_sync(database_url: str | None) -> None:
    cfg = Config(str(_ALEMBIC_INI))
    if database_url is not None:
        cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")


async def run_migrations(database_url: str | None = None) -> None:
    """Run ``alembic upgrade head`` against the configured DB.

    Pass ``database_url`` to override what ``alembic/env.py`` would otherwise
    pull from ``settings.database_url`` — useful for tests. Offloaded to a
    thread because Alembic's online migration runner calls ``asyncio.run()``
    internally, which fails when invoked from a running event loop.
    """
    log.info("auto_migrate.start", database_url=database_url or "<settings.database_url>")
    await asyncio.to_thread(_upgrade_sync, database_url)
    log.info("auto_migrate.done")
