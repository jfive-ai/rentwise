"""Tests for SearchRepo."""

from __future__ import annotations

import pytest

from rentwise.storage.repositories import CachedSearch, SearchRepo


@pytest.mark.asyncio
async def test_save_and_load_search(session):
    repo = SearchRepo(session)
    await repo.upsert(
        CachedSearch(
            cache_key="abc",
            query_json='{"x":1}',
            listing_ids=["id1", "id2"],
            total_count=2,
        )
    )
    await session.commit()
    fetched = await repo.get("abc")
    assert fetched is not None
    assert fetched.listing_ids == ["id1", "id2"]
    assert fetched.total_count == 2


@pytest.mark.asyncio
async def test_missing_cache_key_returns_none(session):
    repo = SearchRepo(session)
    assert await repo.get("nope") is None


@pytest.mark.asyncio
async def test_upsert_overwrites(session):
    repo = SearchRepo(session)
    await repo.upsert(CachedSearch("k", "{}", ["a"], 1))
    await session.commit()
    await repo.upsert(CachedSearch("k", "{}", ["a", "b"], 2))
    await session.commit()
    fetched = await repo.get("k")
    assert fetched.listing_ids == ["a", "b"]
    assert fetched.total_count == 2
