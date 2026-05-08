"""Phase 5 PR-B: alert_log dedup table.

Revision ID: 0008_alerts
Revises: 0007_saved_searches
Create Date: 2026-05-08
"""

from __future__ import annotations

from alembic import op

revision = "0008_alerts"
down_revision = "0007_saved_searches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Composite PK on (cache_key, listing_id) — re-running the same saved
    # search against the same listing must produce zero new alerts.
    op.execute(
        """
        CREATE TABLE alert_log (
            cache_key   TEXT NOT NULL,
            listing_id  TEXT NOT NULL,
            alerted_at  TEXT NOT NULL,
            channel     TEXT NOT NULL DEFAULT 'email',
            PRIMARY KEY (cache_key, listing_id),
            FOREIGN KEY (cache_key) REFERENCES searches(cache_key)
        )
        """
    )
    op.execute("CREATE INDEX idx_alert_log_cache_key ON alert_log(cache_key)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_alert_log_cache_key")
    op.execute("DROP TABLE IF EXISTS alert_log")
