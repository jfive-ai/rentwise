"""Phase 2 LLM settings table.

Revision ID: 0002_llm_settings
Revises: 0001_initial
Create Date: 2026-05-06
"""

from __future__ import annotations

from alembic import op

revision = "0002_llm_settings"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE llm_settings (
            id                            INTEGER PRIMARY KEY CHECK (id = 1),
            primary_model                 TEXT NOT NULL,
            primary_api_key_encrypted     TEXT,
            fallback_model                TEXT,
            fallback_api_key_encrypted    TEXT,
            custom_base_url               TEXT,
            timeout_seconds               INTEGER NOT NULL DEFAULT 30,
            updated_at                    TEXT NOT NULL
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS llm_settings")
