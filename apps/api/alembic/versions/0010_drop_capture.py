"""Phase 8 PR-B: drop the browser-extension capture schema.

Revision ID: 0010_drop_capture
Revises: 0009_web_push
Create Date: 2026-05-08

The browser extension is retired (see ``docs/roadmap.md`` Phase 8).
This migration removes the schema artifacts that only existed to
support it:

* ``capture_pairing`` table — singleton row holding the shared secret
  the extension used to authenticate against ``/capture``.
* ``listings.capture_method`` column — discriminator that only ever
  held ``'server'`` or ``'extension'``. Now obsolete: every row comes
  from a server-side adapter.
* ``listings.first_seen_at`` column — was written by both the server
  upsert and the (now-removed) extension upsert, but never read
  anywhere in business logic. A grep across the repo confirms no
  SELECT/ORDER BY/comparison on this column. Dropping it keeps the
  schema honest; if we want a created-vs-updated distinction later,
  ``created_at`` already covers it.

SQLite >= 3.35 supports ``ALTER TABLE ... DROP COLUMN`` natively, which
the project requires (current SQLite is 3.51). The downgrade path
recreates the schema in the shape Phase 3's ``0003_capture.py`` left
it; the data is not recoverable.
"""

from __future__ import annotations

from alembic import op

revision = "0010_drop_capture"
down_revision = "0009_web_push"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ----------------------------------------------------------------
    # 1) capture_pairing - singleton table, simple drop.
    # ----------------------------------------------------------------
    op.execute("DROP TABLE IF EXISTS capture_pairing")

    # ----------------------------------------------------------------
    # 2) listings columns. Drop the index first; SQLite errors if you
    # try to drop a column referenced by an index.
    # ----------------------------------------------------------------
    op.execute("DROP INDEX IF EXISTS idx_listings_capture_method")
    op.execute("ALTER TABLE listings DROP COLUMN capture_method")
    op.execute("ALTER TABLE listings DROP COLUMN first_seen_at")


def downgrade() -> None:
    # Recreate the columns + index in the shape 0003_capture left them.
    # Defaults make the ALTER non-failing on existing rows: server-row
    # default for capture_method, CURRENT_TIMESTAMP for first_seen_at
    # (we lost the original values; this is a best-effort restore).
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
