"""Phase 3 capture support: capture_method + first_seen_at + capture_pairing.

Revision ID: 0003_capture
Revises: 0002_llm_settings
Create Date: 2026-05-07
"""

from __future__ import annotations

from alembic import op

revision = "0003_capture"
down_revision = "0002_llm_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE listings ADD COLUMN capture_method TEXT "
        "NOT NULL DEFAULT 'server' "
        "CHECK (capture_method IN ('server', 'extension'))"
    )
    op.execute(
        "ALTER TABLE listings ADD COLUMN first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
    )
    op.execute("CREATE INDEX idx_listings_capture_method ON listings(capture_method)")

    op.execute(
        """
        CREATE TABLE capture_pairing (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            token       TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            rotated_at  TEXT
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS capture_pairing")
    op.execute("DROP INDEX IF EXISTS idx_listings_capture_method")
    # SQLite < 3.35 cannot DROP COLUMN without a table rebuild; leave the
    # added columns in place on downgrade. Acceptable for MVP.
