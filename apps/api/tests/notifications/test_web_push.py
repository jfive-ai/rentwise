"""WebPushNotifier tests (Phase 5 PR-C).

pywebpush is patched in every case — the wire protocol isn't what we're
testing here, just the dispatch + prune-on-dead-subscription glue.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from rentwise.notifications.email import EmailAlert, NotifierError
from rentwise.notifications.web_push import VapidConfig, WebPushNotifier
from rentwise.storage.repositories import WebPushSubscriptionRepo


def _alert(to: str = "me@example.com") -> EmailAlert:
    return EmailAlert(
        to=to,
        subject="RentWise: 1 new listing for Kits 2br",
        text_body=(
            "1 new match for: Kits 2br\n"
            "\n"
            "- Listing 1 · 2 bd · $2,800 · 1234 W 4th Ave\n"
            "  https://example.com/listing/1\n"
            "\n"
            "View on RentWise: https://app.example/?saved=k1"
        ),
        html_body="<p>...</p>",
    )


def _vapid() -> VapidConfig:
    return VapidConfig(
        public_key="pub",
        private_key="priv",
        contact="mailto:contact@example.com",
    )


@pytest.fixture
async def seeded_repo(session):
    repo = WebPushSubscriptionRepo(session)
    await repo.upsert(
        endpoint="https://push.example/a",
        p256dh="p1",
        auth="a1",
        alert_email="me@example.com",
        label="Browser A",
    )
    await repo.upsert(
        endpoint="https://push.example/b",
        p256dh="p2",
        auth="a2",
        alert_email="me@example.com",
        label="Browser B",
    )
    return repo


@pytest.mark.asyncio
async def test_no_subs_for_email_is_noop(session) -> None:
    repo = WebPushSubscriptionRepo(session)
    notifier = WebPushNotifier(repo=repo, vapid=_vapid())
    with patch("rentwise.notifications.web_push.webpush") as mock_push:
        await notifier.send_alert(_alert(to="nobody@example.com"))
    mock_push.assert_not_called()


@pytest.mark.asyncio
async def test_send_alert_fans_out_to_every_sub(seeded_repo) -> None:
    notifier = WebPushNotifier(repo=seeded_repo, vapid=_vapid())
    with patch("rentwise.notifications.web_push.webpush") as mock_push:
        await notifier.send_alert(_alert())
    assert mock_push.call_count == 2

    # Every call gets a JSON payload with title + body + click URL.
    first_call = mock_push.call_args_list[0]
    payload = json.loads(first_call.kwargs["data"])
    assert payload["title"] == "RentWise: 1 new listing for Kits 2br"
    assert payload["url"] == "https://app.example/?saved=k1"
    assert payload["body"]


@pytest.mark.asyncio
async def test_410_gone_prunes_subscription(seeded_repo, session) -> None:
    """RFC 8030: a 410 means the user unsubscribed in the browser."""
    from pywebpush import WebPushException

    response = MagicMock()
    response.status_code = 410
    response.text = "gone"

    notifier = WebPushNotifier(repo=seeded_repo, vapid=_vapid())
    with patch(
        "rentwise.notifications.web_push.webpush",
        side_effect=WebPushException("gone", response=response),
    ):
        await notifier.send_alert(_alert())

    # Both endpoints in the seed file return 410 → both rows pruned.
    remaining = await seeded_repo.list_for_email("me@example.com")
    assert remaining == []


@pytest.mark.asyncio
async def test_404_also_prunes(seeded_repo) -> None:
    from pywebpush import WebPushException

    response = MagicMock()
    response.status_code = 404
    notifier = WebPushNotifier(repo=seeded_repo, vapid=_vapid())
    with patch(
        "rentwise.notifications.web_push.webpush",
        side_effect=WebPushException("nope", response=response),
    ):
        await notifier.send_alert(_alert())
    assert await seeded_repo.list_for_email("me@example.com") == []


@pytest.mark.asyncio
async def test_5xx_raises_notifier_error(seeded_repo) -> None:
    from pywebpush import WebPushException

    response = MagicMock()
    response.status_code = 503
    notifier = WebPushNotifier(repo=seeded_repo, vapid=_vapid())
    with patch(
        "rentwise.notifications.web_push.webpush",
        side_effect=WebPushException("busy", response=response),
    ):
        with pytest.raises(NotifierError):
            await notifier.send_alert(_alert())

    # Subscriptions preserved — transient 5xx is not a reason to prune.
    assert len(await seeded_repo.list_for_email("me@example.com")) == 2


@pytest.mark.asyncio
async def test_partial_failure_still_records_delivery(seeded_repo) -> None:
    """If sub A fails 5xx but sub B succeeds, dispatch is still considered
    a success (delivered>0) and the runner records dedup."""
    from pywebpush import WebPushException

    bad_response = MagicMock()
    bad_response.status_code = 503

    call_count = {"n": 0}

    def side_effect(**_kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise WebPushException("busy", response=bad_response)
        return MagicMock()

    notifier = WebPushNotifier(repo=seeded_repo, vapid=_vapid())
    with patch("rentwise.notifications.web_push.webpush", side_effect=side_effect):
        # No exception — at least one delivery succeeded.
        await notifier.send_alert(_alert())

    # The failing sub stays — we only prune on 4xx-class deadness.
    assert len(await seeded_repo.list_for_email("me@example.com")) == 2
