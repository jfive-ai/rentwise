"""SearchRepo.save / list_saved / delete_saved (Phase 5 PR-A)."""

from __future__ import annotations

import json

import pytest

from rentwise.storage.repositories import CachedSearch, SearchRepo


async def _seed(repo: SearchRepo, key: str = "k1") -> None:
    """Seed an unsaved cache row that ``save`` can flip to saved."""
    await repo.upsert(
        CachedSearch(
            cache_key=key,
            query_json=json.dumps({"bedrooms_min": 2}),
            listing_ids=["a", "b"],
            total_count=2,
            is_saved=False,
        )
    )


@pytest.mark.asyncio
async def test_save_returns_none_for_unknown_cache_key(session) -> None:
    repo = SearchRepo(session)
    out = await repo.save("missing", label="x")
    assert out is None


@pytest.mark.asyncio
async def test_save_sets_label_and_alert_metadata(session) -> None:
    repo = SearchRepo(session)
    await _seed(repo)

    out = await repo.save(
        "k1",
        label="2br Kits",
        alert_enabled=True,
        alert_email="me@example.com",
        cadence_minutes=30,
    )
    assert out is not None
    assert out.user_label == "2br Kits"
    assert out.alert_enabled is True
    assert out.alert_email == "me@example.com"
    assert out.alert_cadence_minutes == 30


@pytest.mark.asyncio
async def test_list_saved_omits_unsaved_rows(session) -> None:
    repo = SearchRepo(session)
    await _seed(repo, "k1")
    await _seed(repo, "k2")
    await repo.save("k1", label="kept")

    saved = await repo.list_saved()
    assert [s.cache_key for s in saved] == ["k1"]


@pytest.mark.asyncio
async def test_delete_saved_unsets_flags_but_keeps_row(session) -> None:
    repo = SearchRepo(session)
    await _seed(repo, "k1")
    await repo.save("k1", label="going away", alert_enabled=True, alert_email="x@x")

    deleted = await repo.delete_saved("k1")
    assert deleted is True

    # Row still exists (cache row preserved); just no longer saved.
    cached = await repo.get("k1")
    assert cached is not None
    assert cached.is_saved is False
    saved = await repo.list_saved()
    assert saved == []


@pytest.mark.asyncio
async def test_delete_saved_returns_false_when_row_was_not_saved(session) -> None:
    repo = SearchRepo(session)
    await _seed(repo, "k1")
    deleted = await repo.delete_saved("k1")
    assert deleted is False


@pytest.mark.asyncio
async def test_delete_saved_returns_false_for_unknown_key(session) -> None:
    repo = SearchRepo(session)
    deleted = await repo.delete_saved("nope")
    assert deleted is False


@pytest.mark.asyncio
async def test_resaving_preserves_cadence_choice(session) -> None:
    """Save → delete → save: cadence the user picked the first time
    persists across the round-trip (we don't reset it on delete)."""
    repo = SearchRepo(session)
    await _seed(repo, "k1")
    await repo.save("k1", label="first", cadence_minutes=15)
    await repo.delete_saved("k1")
    out = await repo.save("k1", label="second")
    assert out is not None
    assert out.alert_cadence_minutes == 15


@pytest.mark.asyncio
async def test_list_saved_orders_by_last_run_desc(session) -> None:
    """Most-recently-run saved search comes first."""
    repo = SearchRepo(session)
    await _seed(repo, "old")
    await repo.save("old", label="old")

    # Bump last_run_at on a second saved search by re-upserting it.
    await _seed(repo, "new")
    await repo.upsert(
        CachedSearch(
            cache_key="new",
            query_json=json.dumps({"bedrooms_min": 1}),
            listing_ids=["c"],
            total_count=1,
        )
    )
    await repo.save("new", label="new")

    saved = await repo.list_saved()
    assert next(s.cache_key for s in saved) == "new"
