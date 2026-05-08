"""Phase 4 PR-C: photo perceptual hash + dedup support.

Revision ID: 0006_dedup
Revises: 0005_listings_transit
Create Date: 2026-05-08
"""

from __future__ import annotations

from alembic import op

revision = "0006_dedup"
down_revision = "0005_listings_transit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE listings ADD COLUMN phash TEXT")
    # Indexed for the dedup candidate lookup, which scans by
    # address_normalized to find listings that might be the same property.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_listings_address_normalized ON listings(address_normalized)"
    )

    op.execute(
        """
        CREATE TABLE photo_hash_cache (
            url           TEXT PRIMARY KEY,
            phash         TEXT,
            fetched_at    TEXT NOT NULL,
            stale_after   TEXT NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX idx_photo_hash_cache_stale ON photo_hash_cache(stale_after)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_photo_hash_cache_stale")
    op.execute("DROP TABLE IF EXISTS photo_hash_cache")
    op.execute("DROP INDEX IF EXISTS idx_listings_address_normalized")
    # SQLite < 3.35 cannot DROP COLUMN without a table rebuild; leave
    # `phash` in place on downgrade. Acceptable for MVP.
