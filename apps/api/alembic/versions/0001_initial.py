"""Phase 1 initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-06
"""

from __future__ import annotations

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE listings (
            id                    TEXT PRIMARY KEY,
            canonical_id          TEXT,
            source                TEXT NOT NULL,
            source_listing_id     TEXT NOT NULL,
            source_url            TEXT NOT NULL,
            title                 TEXT NOT NULL,
            snippet               TEXT,
            address_raw           TEXT,
            address_normalized    TEXT,
            neighborhood          TEXT,
            lat                   REAL,
            lon                   REAL,
            bedrooms              REAL,
            bathrooms             REAL,
            price_cad             INTEGER,
            pets_allowed          INTEGER,
            furnished             INTEGER,
            available_date        TEXT,
            posted_at             TEXT NOT NULL,
            last_seen_at          TEXT NOT NULL,
            catchment_elementary  TEXT,
            catchment_middle      TEXT,
            catchment_secondary   TEXT,
            photo_urls_json       TEXT,
            raw_metadata_json     TEXT,
            created_at            TEXT NOT NULL,
            updated_at            TEXT NOT NULL,
            UNIQUE (source, source_listing_id)
        )
    """)
    op.execute("CREATE INDEX idx_listings_canonical    ON listings(canonical_id)")
    op.execute("CREATE INDEX idx_listings_posted_at    ON listings(posted_at DESC)")
    op.execute("CREATE INDEX idx_listings_price        ON listings(price_cad)")
    op.execute("CREATE INDEX idx_listings_bedrooms     ON listings(bedrooms)")
    op.execute("CREATE INDEX idx_listings_catchment_elem ON listings(catchment_elementary)")
    op.execute("CREATE INDEX idx_listings_catchment_sec  ON listings(catchment_secondary)")

    op.execute("""
        CREATE VIRTUAL TABLE listings_fts USING fts5(
            title, snippet, neighborhood,
            content='listings', content_rowid='rowid',
            tokenize='unicode61 remove_diacritics 2'
        )
    """)
    op.execute("""
        CREATE TRIGGER listings_ai AFTER INSERT ON listings BEGIN
            INSERT INTO listings_fts(rowid, title, snippet, neighborhood)
            VALUES (new.rowid, new.title, new.snippet, new.neighborhood);
        END
    """)
    op.execute("""
        CREATE TRIGGER listings_ad AFTER DELETE ON listings BEGIN
            INSERT INTO listings_fts(listings_fts, rowid, title, snippet, neighborhood)
            VALUES ('delete', old.rowid, old.title, old.snippet, old.neighborhood);
        END
    """)
    op.execute("""
        CREATE TRIGGER listings_au AFTER UPDATE ON listings BEGIN
            INSERT INTO listings_fts(listings_fts, rowid, title, snippet, neighborhood)
            VALUES ('delete', old.rowid, old.title, old.snippet, old.neighborhood);
            INSERT INTO listings_fts(rowid, title, snippet, neighborhood)
            VALUES (new.rowid, new.title, new.snippet, new.neighborhood);
        END
    """)

    op.execute("""
        CREATE TABLE canonical_listings (
            id                  TEXT PRIMARY KEY,
            primary_listing_id  TEXT NOT NULL REFERENCES listings(id),
            created_at          TEXT NOT NULL
        )
    """)

    op.execute("""
        CREATE TABLE searches (
            cache_key         TEXT PRIMARY KEY,
            query_json        TEXT NOT NULL,
            last_run_at       TEXT NOT NULL,
            listing_ids_json  TEXT NOT NULL,
            total_count       INTEGER NOT NULL,
            is_saved          INTEGER NOT NULL DEFAULT 0,
            user_label        TEXT
        )
    """)
    op.execute("CREATE INDEX idx_searches_last_run ON searches(last_run_at)")

    op.execute("""
        CREATE TABLE source_health (
            source                TEXT PRIMARY KEY,
            status                TEXT NOT NULL,
            last_success_at       TEXT,
            last_error_at         TEXT,
            last_error_message    TEXT,
            consecutive_failures  INTEGER NOT NULL DEFAULT 0,
            updated_at            TEXT NOT NULL
        )
    """)

    # Phase 5 stubs
    op.execute("CREATE TABLE alerts (id TEXT PRIMARY KEY)")
    op.execute("CREATE TABLE users  (id TEXT PRIMARY KEY)")


def downgrade() -> None:
    for stmt in [
        "DROP TABLE IF EXISTS users",
        "DROP TABLE IF EXISTS alerts",
        "DROP TABLE IF EXISTS source_health",
        "DROP TABLE IF EXISTS searches",
        "DROP TABLE IF EXISTS canonical_listings",
        "DROP TRIGGER IF EXISTS listings_au",
        "DROP TRIGGER IF EXISTS listings_ad",
        "DROP TRIGGER IF EXISTS listings_ai",
        "DROP TABLE IF EXISTS listings_fts",
        "DROP TABLE IF EXISTS listings",
    ]:
        op.execute(stmt)
