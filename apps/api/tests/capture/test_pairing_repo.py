"""Tests for CapturePairingRepo — get-or-create singleton, rotate."""

from __future__ import annotations

import pytest

from rentwise.capture.pairing import CapturePairingRepo


@pytest.mark.asyncio
async def test_get_or_create_creates_when_absent(session):
    repo = CapturePairingRepo(session)
    record = await repo.get_or_create()
    await session.commit()

    assert record.token
    assert len(record.token) >= 32
    assert record.rotated_at is None


@pytest.mark.asyncio
async def test_get_or_create_is_idempotent(session):
    repo = CapturePairingRepo(session)
    first = await repo.get_or_create()
    await session.commit()
    second = await repo.get_or_create()
    await session.commit()

    assert first.token == second.token


@pytest.mark.asyncio
async def test_rotate_replaces_token_and_sets_rotated_at(session):
    repo = CapturePairingRepo(session)
    first = await repo.get_or_create()
    await session.commit()

    rotated = await repo.rotate()
    await session.commit()

    assert rotated.token != first.token
    assert rotated.rotated_at is not None


@pytest.mark.asyncio
async def test_get_returns_none_when_unset(session):
    repo = CapturePairingRepo(session)
    assert await repo.get() is None
