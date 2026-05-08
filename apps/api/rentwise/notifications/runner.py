"""AlertRunner: re-runs a saved search, dispatches alerts for new
listings, records the dedup ledger.

The runner is decoupled from the scheduler so a manual ``/run-now``
endpoint and the scheduler tick share the exact same code path.

Multi-channel (Phase 5 PR-C): the runner takes a dict
``{channel_name: Notifier}``. Each channel maintains its own dedup
ledger, so adding web push to a saved search that previously only
emailed still notifies via push for the existing backlog. Per-channel
failure is isolated — an SMTP outage doesn't block web-push delivery.

Failure modes:

- Aggregator raises → no notification, no dedup row written on any
  channel. Next tick will retry naturally.
- A channel's notifier raises → that channel's dedup row is **not**
  written for the listings in that dispatch, so the next tick will
  retry. Other channels still proceed.
- ``alert_enabled=False`` or ``alert_email is None`` → silent skip.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import structlog

from rentwise.models import (
    NormalizedListing,
    NormalizedQuery,
    SearchRequest,
    SearchResponse,
)
from rentwise.notifications.email import (
    Notifier,
    NotifierError,
    compose_alert,
)
from rentwise.storage.repositories import (
    AlertLogRepo,
    SavedSearch,
    SearchRepo,
)

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RunResult:
    cache_key: str
    new_listings: int
    sent: int  # max delivered count across channels
    skipped: bool  # True when alert_enabled / alert_email gates the run
    error: str | None = None
    sent_by_channel: dict[str, int] | None = None
    error_by_channel: dict[str, str] | None = None


class Aggregator(Protocol):
    """Minimal aggregator surface the runner needs."""

    async def search(self, req: SearchRequest) -> SearchResponse: ...


@dataclass(frozen=True)
class RunnerConfig:
    app_base_url: str = "http://localhost:8081"
    max_listings_per_email: int = 25


class AlertRunner:
    def __init__(
        self,
        *,
        aggregator: Aggregator,
        alert_log: AlertLogRepo,
        config: RunnerConfig | None = None,
        notifier: Notifier | None = None,
        notifiers: dict[str, Notifier] | None = None,
    ) -> None:
        """Multi-channel runner.

        Pass either ``notifier`` (legacy single-channel email) **or**
        ``notifiers`` (dict[channel, Notifier]) but not both. The legacy
        form maps to ``{"email": notifier}`` so existing call sites keep
        working without changes.
        """
        if notifier is not None and notifiers is not None:
            raise ValueError("pass notifier OR notifiers, not both")
        if notifiers is not None:
            self._channels = dict(notifiers)
        elif notifier is not None:
            self._channels = {"email": notifier}
        else:
            self._channels = {}
        self.aggregator = aggregator
        self.alert_log = alert_log
        self.config = config or RunnerConfig()

    async def check_one(self, saved: SavedSearch) -> RunResult:
        if not saved.alert_enabled or saved.alert_email is None:
            return RunResult(cache_key=saved.cache_key, new_listings=0, sent=0, skipped=True)
        if not self._channels:
            return RunResult(cache_key=saved.cache_key, new_listings=0, sent=0, skipped=True)

        query = NormalizedQuery.model_validate_json(saved.query_json)
        try:
            resp = await self.aggregator.search(SearchRequest(query=query, limit=200, offset=0))
        except Exception as exc:
            log.warning("alert.search_failed", cache_key=saved.cache_key, error=str(exc))
            return RunResult(
                cache_key=saved.cache_key,
                new_listings=0,
                sent=0,
                skipped=False,
                error=str(exc),
            )

        # Compute per-channel delta — each channel has its own ledger.
        sent_by_channel: dict[str, int] = {}
        error_by_channel: dict[str, str] = {}
        max_new_listings = 0

        for channel, notifier in self._channels.items():
            already = await self.alert_log.get_alerted_ids(saved.cache_key, channel=channel)
            new_listings = [li for li in resp.listings if str(li.id) not in already]
            max_new_listings = max(max_new_listings, len(new_listings))
            if not new_listings:
                sent_by_channel[channel] = 0
                continue

            batch = new_listings[: self.config.max_listings_per_email]
            try:
                await self._dispatch(notifier, saved, batch)
            except NotifierError as exc:
                log.warning(
                    "alert.notifier_failed",
                    cache_key=saved.cache_key,
                    channel=channel,
                    error=str(exc),
                )
                error_by_channel[channel] = str(exc)
                sent_by_channel[channel] = 0
                continue

            await self.alert_log.record_alerted(
                saved.cache_key,
                [str(li.id) for li in batch],
                channel=channel,
            )
            sent_by_channel[channel] = len(batch)
            log.info(
                "alert.sent",
                cache_key=saved.cache_key,
                channel=channel,
                sent=len(batch),
                total_new=len(new_listings),
            )

        # Aggregate `sent` is the max across channels — gives the caller
        # a "did anything go out?" signal without summing duplicates
        # across channels.
        return RunResult(
            cache_key=saved.cache_key,
            new_listings=max_new_listings,
            sent=max(sent_by_channel.values(), default=0),
            skipped=False,
            error=next(iter(error_by_channel.values()), None),
            sent_by_channel=sent_by_channel,
            error_by_channel=error_by_channel or None,
        )

    async def _dispatch(
        self,
        notifier: Notifier,
        saved: SavedSearch,
        batch: list[NormalizedListing],
    ) -> None:
        assert saved.alert_email is not None  # narrowed by check_one
        alert = compose_alert(
            label=saved.user_label,
            listings=batch,
            app_base_url=self.config.app_base_url,
            cache_key=saved.cache_key,
            to=saved.alert_email,
        )
        await notifier.send_alert(alert)

    async def check_all(self, search_repo: SearchRepo) -> list[RunResult]:
        """Run every alert-enabled saved search once."""
        out: list[RunResult] = []
        for saved in await search_repo.list_saved():
            if not saved.alert_enabled:
                continue
            out.append(await self.check_one(saved))
        return out


# Re-exported for convenience — tests import this directly.
__all__ = ["Aggregator", "AlertRunner", "RunResult", "RunnerConfig"]
