"""Phase 5 PR-A: alert columns on saved searches.

Revision ID: 0007_saved_searches
Revises: 0006_dedup
Create Date: 2026-05-08
"""

from __future__ import annotations

from alembic import op

revision = "0007_saved_searches"
down_revision = "0006_dedup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The base table already has `is_saved` (0/1) and `user_label`. PR-A
    # adds the alert wiring; PR-B will read these columns to decide
    # which saved searches to schedule + where to deliver notifications.
    op.execute("ALTER TABLE searches ADD COLUMN alert_enabled INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE searches ADD COLUMN alert_email TEXT")
    op.execute("ALTER TABLE searches ADD COLUMN alert_cadence_minutes INTEGER NOT NULL DEFAULT 60")
    op.execute("CREATE INDEX IF NOT EXISTS idx_searches_is_saved ON searches(is_saved)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_searches_is_saved")
    # SQLite < 3.35 cannot DROP COLUMN without a table rebuild; leave
    # the alert columns in place on downgrade. Acceptable for MVP.
