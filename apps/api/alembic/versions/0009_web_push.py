"""Phase 5 PR-C: web push subscriptions + per-channel alert dedup.

Revision ID: 0009_web_push
Revises: 0008_alerts
Create Date: 2026-05-08

Adds two changes that together let web push share the alert pipeline
with email:

1. ``web_push_subscriptions`` table — one row per browser/origin
   subscription, routed by ``alert_email`` (the same key the saved
   search uses).

2. Rebuilds ``alert_log`` so its PK is
   ``(cache_key, listing_id, channel)``. PR-B's PK was
   ``(cache_key, listing_id)``, which would collide between email and
   web push for the same listing. Per-channel dedup matches the user
   expectation that enabling web push later should still notify on
   listings the user previously got an email for.
"""

from __future__ import annotations

from alembic import op

revision = "0009_web_push"
down_revision = "0008_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ----------------------------------------------------------------
    # 1) web_push_subscriptions
    # ----------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE web_push_subscriptions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint        TEXT NOT NULL UNIQUE,
            p256dh          TEXT NOT NULL,
            auth            TEXT NOT NULL,
            alert_email     TEXT,
            label           TEXT,
            created_at      TEXT NOT NULL,
            last_seen_at    TEXT NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX idx_web_push_subs_email ON web_push_subscriptions(alert_email)")

    # ----------------------------------------------------------------
    # 2) Rebuild alert_log with (cache_key, listing_id, channel) PK.
    # SQLite can't alter the PK in place; rebuild + copy.
    # ----------------------------------------------------------------
    op.execute("DROP INDEX IF EXISTS idx_alert_log_cache_key")
    op.execute("ALTER TABLE alert_log RENAME TO alert_log_v1")
    op.execute(
        """
        CREATE TABLE alert_log (
            cache_key   TEXT NOT NULL,
            listing_id  TEXT NOT NULL,
            alerted_at  TEXT NOT NULL,
            channel     TEXT NOT NULL DEFAULT 'email',
            PRIMARY KEY (cache_key, listing_id, channel),
            FOREIGN KEY (cache_key) REFERENCES searches(cache_key)
        )
        """
    )
    op.execute(
        "INSERT INTO alert_log (cache_key, listing_id, alerted_at, channel) "
        "SELECT cache_key, listing_id, alerted_at, channel FROM alert_log_v1"
    )
    op.execute("DROP TABLE alert_log_v1")
    op.execute("CREATE INDEX idx_alert_log_cache_key ON alert_log(cache_key)")


def downgrade() -> None:
    # web_push_subscriptions: simple drop.
    op.execute("DROP INDEX IF EXISTS idx_web_push_subs_email")
    op.execute("DROP TABLE IF EXISTS web_push_subscriptions")

    # alert_log: collapse back to (cache_key, listing_id) PK. Any
    # rows that existed twice across channels collapse via INSERT OR
    # IGNORE — first wins.
    op.execute("DROP INDEX IF EXISTS idx_alert_log_cache_key")
    op.execute("ALTER TABLE alert_log RENAME TO alert_log_v2")
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
    op.execute(
        "INSERT OR IGNORE INTO alert_log "
        "(cache_key, listing_id, alerted_at, channel) "
        "SELECT cache_key, listing_id, alerted_at, channel FROM alert_log_v2"
    )
    op.execute("DROP TABLE alert_log_v2")
    op.execute("CREATE INDEX idx_alert_log_cache_key ON alert_log(cache_key)")
