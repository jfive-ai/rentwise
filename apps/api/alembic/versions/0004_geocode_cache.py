"""Phase 4 PR-A: persistent geocode cache.

Revision ID: 0004_geocode_cache
Revises: 0003_capture
Create Date: 2026-05-07
"""

from __future__ import annotations

from alembic import op

revision = "0004_geocode_cache"
down_revision = "0003_capture"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keyed on the normalized address (canonical form from
    # rentwise.enrichment.address.normalize_address). One row per
    # distinct address; lat/lon nullable so we can record "not found"
    # negatives and avoid re-querying the provider for hopeless inputs.
    op.execute(
        """
        CREATE TABLE geocode_cache (
            address_key   TEXT PRIMARY KEY,
            lat           REAL,
            lon           REAL,
            provider      TEXT NOT NULL,
            fetched_at    TEXT NOT NULL,
            stale_after   TEXT NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX idx_geocode_cache_stale ON geocode_cache(stale_after)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_geocode_cache_stale")
    op.execute("DROP TABLE IF EXISTS geocode_cache")
