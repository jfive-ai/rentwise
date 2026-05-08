"""AlertLogRepo dedup tests (Phase 5 PR-B)."""

from __future__ import annotations

import pytest

from rentwise.storage.repositories import AlertLogRepo


@pytest.mark.asyncio
async def test_empty_for_unknown_key(session) -> None:
    repo = AlertLogRepo(session)
    assert await repo.get_alerted_ids("nope") == set()


@pytest.mark.asyncio
async def test_record_then_get(session) -> None:
    repo = AlertLogRepo(session)
    await repo.record_alerted("k1", ["a", "b", "c"])
    out = await repo.get_alerted_ids("k1")
    assert out == {"a", "b", "c"}


@pytest.mark.asyncio
async def test_record_is_per_cache_key(session) -> None:
    """Recording listings under one key must not surface under another."""
    repo = AlertLogRepo(session)
    await repo.record_alerted("k1", ["a"])
    await repo.record_alerted("k2", ["b"])
    assert await repo.get_alerted_ids("k1") == {"a"}
    assert await repo.get_alerted_ids("k2") == {"b"}


@pytest.mark.asyncio
async def test_record_idempotent_for_same_listing(session) -> None:
    """The same listing recorded twice → still one row."""
    repo = AlertLogRepo(session)
    await repo.record_alerted("k1", ["a"])
    await repo.record_alerted("k1", ["a"])
    assert await repo.get_alerted_ids("k1") == {"a"}


@pytest.mark.asyncio
async def test_record_partial_overlap_only_writes_new_rows(session) -> None:
    """If two of three listings are already recorded, the third gets a
    fresh row and the existing two are left alone (no PK violation)."""
    repo = AlertLogRepo(session)
    await repo.record_alerted("k1", ["a", "b"])
    await repo.record_alerted("k1", ["a", "b", "c"])
    assert await repo.get_alerted_ids("k1") == {"a", "b", "c"}


@pytest.mark.asyncio
async def test_record_empty_list_is_noop(session) -> None:
    repo = AlertLogRepo(session)
    await repo.record_alerted("k1", [])
    assert await repo.get_alerted_ids("k1") == set()


@pytest.mark.asyncio
async def test_channel_defaults_to_email(session) -> None:
    """Channel column default — PR-C will use 'web_push' alongside."""
    repo = AlertLogRepo(session)
    await repo.record_alerted("k1", ["a"])

    # Read raw via the ORM model to assert the default.
    from sqlalchemy import select

    from rentwise.storage.models import AlertLogRow

    row = (
        await session.execute(
            select(AlertLogRow).where(AlertLogRow.cache_key == "k1", AlertLogRow.listing_id == "a")
        )
    ).scalar_one()
    assert row.channel == "email"
