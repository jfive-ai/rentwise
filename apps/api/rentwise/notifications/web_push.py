"""Web push notifier (Phase 5 PR-C).

Implements the existing :class:`Notifier` protocol from
:mod:`notifications.email`, so :class:`AlertRunner` doesn't need to
know whether it's dispatching email, web push, or both — that's a
``MultiNotifier`` decision.

For each saved-search alert this class:

1. Looks up subscriptions whose ``alert_email`` matches the alert's
   ``to`` field. (We re-use ``alert_email`` as the routing key
   because the saved search is keyed on it; one user can have
   multiple browsers registered against the same email.)
2. Sends the encrypted payload to each via :func:`pywebpush.webpush`,
   in a worker thread so the FastAPI loop stays free.
3. On 410 Gone or 404, deletes the dead subscription row. On other
   errors, raises :class:`NotifierError` so the runner skips the
   dedup write.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import structlog
from pywebpush import WebPushException, webpush

from rentwise.notifications.email import EmailAlert, NotifierError
from rentwise.storage.repositories import WebPushSubscriptionRepo

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class VapidConfig:
    public_key: str
    private_key: str
    contact: str  # mailto:... or https://... per RFC 8292


class WebPushNotifier:
    def __init__(
        self,
        *,
        repo: WebPushSubscriptionRepo,
        vapid: VapidConfig,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._repo = repo
        self._vapid = vapid
        self._timeout = timeout_seconds

    async def send_alert(self, alert: EmailAlert) -> None:
        subs = await self._repo.list_for_email(alert.to)
        if not subs:
            log.info("web_push.no_subs", to=alert.to)
            return

        payload = json.dumps(
            {
                "title": alert.subject,
                "body": _short_body(alert.text_body),
                "url": _extract_url(alert),
            }
        )

        first_error: Exception | None = None
        delivered = 0
        for sub in subs:
            try:
                await asyncio.to_thread(self._send_one, sub.endpoint, sub.p256dh, sub.auth, payload)
                delivered += 1
            except _DeadSubscriptionError:
                log.info("web_push.pruned", endpoint=sub.endpoint)
                await self._repo.delete_by_endpoint(sub.endpoint)
            except Exception as exc:
                log.warning("web_push.send_failed", endpoint=sub.endpoint, error=str(exc))
                if first_error is None:
                    first_error = exc

        # Pure no-op delivery (every sub was dead) is still a "success" —
        # the runner can record dedup. But if we have any active subs and
        # *every* live one failed, surface the first error.
        if delivered == 0 and first_error is not None:
            raise NotifierError(str(first_error)) from first_error

    def _send_one(self, endpoint: str, p256dh: str, auth: str, payload: str) -> None:
        subscription_info = {
            "endpoint": endpoint,
            "keys": {"p256dh": p256dh, "auth": auth},
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=self._vapid.private_key,
                vapid_claims={"sub": self._vapid.contact},
                timeout=self._timeout,
            )
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None) if exc.response else None
            if status in (404, 410):
                raise _DeadSubscriptionError() from exc
            raise


class _DeadSubscriptionError(Exception):
    """Sentinel — signals the caller should prune the subscription row."""


def _short_body(text_body: str) -> str:
    """Take the first non-empty line as the push notification body."""
    for line in text_body.splitlines():
        s = line.strip()
        if s:
            return s[:160]
    return ""


def _extract_url(alert: EmailAlert) -> str | None:
    """The compose_alert text body ends with 'View on RentWise: <url>' —
    pull it out for the service worker to use as the click target."""
    needle = "View on RentWise:"
    for line in alert.text_body.splitlines():
        if needle in line:
            return line.split(needle, 1)[1].strip() or None
    return None
