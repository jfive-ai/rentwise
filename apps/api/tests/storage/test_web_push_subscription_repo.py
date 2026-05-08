"""WebPushSubscriptionRepo round-trip + dedup-on-endpoint tests (Phase 5 PR-C)."""

from __future__ import annotations

import pytest

from rentwise.storage.repositories import WebPushSubscriptionRepo


def _payload(*, endpoint: str = "https://push.example/abc", **overrides):
    base = dict(
        endpoint=endpoint,
        p256dh="p256dh-bytes",
        auth="auth-bytes",
        alert_email="me@example.com",
        label="MacBook Chrome",
    )
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_upsert_creates_then_reads_back(session) -> None:
    repo = WebPushSubscriptionRepo(session)
    sub = await repo.upsert(**_payload())
    assert sub.id > 0
    assert sub.endpoint == "https://push.example/abc"
    assert sub.alert_email == "me@example.com"

    again = await repo.get_by_endpoint("https://push.example/abc")
    assert again is not None
    assert again.id == sub.id


@pytest.mark.asyncio
async def test_upsert_same_endpoint_updates_in_place(session) -> None:
    """Re-subscribing the same browser produces the same row, not duplicates."""
    repo = WebPushSubscriptionRepo(session)
    first = await repo.upsert(**_payload(label="Original"))
    second = await repo.upsert(**_payload(label="Renamed"))
    assert first.id == second.id
    assert second.label == "Renamed"


@pytest.mark.asyncio
async def test_list_for_email_filters_by_alert_email(session) -> None:
    repo = WebPushSubscriptionRepo(session)
    await repo.upsert(**_payload(endpoint="https://push.example/a", alert_email="a@x"))
    await repo.upsert(**_payload(endpoint="https://push.example/b", alert_email="b@x"))
    await repo.upsert(**_payload(endpoint="https://push.example/c", alert_email="a@x"))

    a_subs = await repo.list_for_email("a@x")
    b_subs = await repo.list_for_email("b@x")
    none = await repo.list_for_email("z@x")
    assert {s.endpoint for s in a_subs} == {
        "https://push.example/a",
        "https://push.example/c",
    }
    assert {s.endpoint for s in b_subs} == {"https://push.example/b"}
    assert none == []


@pytest.mark.asyncio
async def test_delete_returns_false_for_unknown_id(session) -> None:
    repo = WebPushSubscriptionRepo(session)
    assert await repo.delete(99999) is False


@pytest.mark.asyncio
async def test_delete_removes_the_row(session) -> None:
    repo = WebPushSubscriptionRepo(session)
    sub = await repo.upsert(**_payload())
    assert await repo.delete(sub.id) is True
    assert await repo.get_by_endpoint(sub.endpoint) is None


@pytest.mark.asyncio
async def test_delete_by_endpoint_used_by_notifier_on_410(session) -> None:
    """The notifier prunes a row when the push service returns 410 Gone."""
    repo = WebPushSubscriptionRepo(session)
    await repo.upsert(**_payload(endpoint="https://push.example/dead"))
    assert await repo.delete_by_endpoint("https://push.example/dead") is True
    # Idempotent — a second 410 doesn't error.
    assert await repo.delete_by_endpoint("https://push.example/dead") is False


@pytest.mark.asyncio
async def test_alert_email_can_be_null(session) -> None:
    """Anonymous subs are allowed (no saved-search routing yet)."""
    repo = WebPushSubscriptionRepo(session)
    sub = await repo.upsert(**_payload(alert_email=None))
    assert sub.alert_email is None
    out = await repo.list_for_email("anything")
    assert out == []
