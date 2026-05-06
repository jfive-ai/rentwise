import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_initial_migration_creates_all_tables(migrated_engine):
    expected = {
        "listings",
        "listings_fts",
        "canonical_listings",
        "searches",
        "source_health",
        "alerts",
        "users",
    }
    async with migrated_engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type IN ('table','view')")
        )
        names = {r[0] for r in rows}
    assert expected.issubset(names)


@pytest.mark.asyncio
async def test_listings_unique_source_constraint(migrated_engine):
    """INSERT OR REPLACE on (source, source_listing_id) collapses dupes."""
    from sqlalchemy import text as t

    async with migrated_engine.begin() as conn:
        ins = (
            "INSERT INTO listings (id, source, source_listing_id, source_url, title, "
            "posted_at, last_seen_at, created_at, updated_at) VALUES "
            "(:id, 'craigslist', '123', 'https://x', 't', '2026-01-01', "
            "'2026-01-01', '2026-01-01', '2026-01-01')"
        )
        await conn.execute(t(ins), {"id": "a"})
        with pytest.raises(Exception, match="UNIQUE"):
            await conn.execute(t(ins), {"id": "b"})
