"""End-to-end check that auto-migrate at startup unbreaks a fresh DB.

Without the migrate-on-startup hook, hitting any endpoint that touches a
table from a migration (e.g. ``/settings/llm`` → ``llm_settings``) on a
freshly-created sqlite file returns 500 (``no such table``). With the hook
the app should migrate during lifespan startup and the same call should
return a clean 404 (no row yet).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def _fresh_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point settings + the cached engine at an empty sqlite file."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}"
    monkeypatch.setattr("rentwise.settings.settings.database_url", db_url)
    monkeypatch.setattr("rentwise.settings.settings.auto_migrate", True)

    # Test fixture in test_settings_endpoints monkey-patches a Fernet key for
    # encryption; do the same here so anything that reads it on startup is
    # safe.
    monkeypatch.setattr(
        "rentwise.llm.settings_crypto.settings.rentwise_settings_encryption_key",
        "M2zZqQrAvFkkr_xWmaVjJqASfh-dhmL7yLQ2hM6oMmU=",
    )

    from rentwise.storage import db as db_mod

    db_mod.get_engine.cache_clear()
    db_mod.get_sessionmaker.cache_clear()
    yield
    db_mod.get_engine.cache_clear()
    db_mod.get_sessionmaker.cache_clear()


def test_settings_llm_returns_404_not_500_on_fresh_db(_fresh_db) -> None:
    from rentwise.main import app

    # `with` block triggers lifespan — startup hooks fire, including
    # _auto_migrate which calls run_migrations() against the patched URL.
    with TestClient(app) as client:
        resp = client.get("/settings/llm")

    # Pre-fix: 500 with "no such table: llm_settings".
    # Post-fix: 404 with detail "no_llm_settings" (table exists, row empty).
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "no_llm_settings"
