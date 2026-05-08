"""Phase 4 PR-B: nearest-transit columns on listings.

Revision ID: 0005_listings_transit
Revises: 0004_geocode_cache
Create Date: 2026-05-08
"""

from __future__ import annotations

from alembic import op

revision = "0005_listings_transit"
down_revision = "0004_geocode_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE listings ADD COLUMN nearest_transit_stop TEXT")
    op.execute("ALTER TABLE listings ADD COLUMN nearest_transit_walk_minutes INTEGER")
    op.execute("ALTER TABLE listings ADD COLUMN nearest_transit_line TEXT")
    op.execute("CREATE INDEX idx_listings_transit_walk ON listings(nearest_transit_walk_minutes)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_listings_transit_walk")
    # SQLite < 3.35 cannot DROP COLUMN without a table rebuild; leave the
    # added columns in place on downgrade. Acceptable for MVP.
