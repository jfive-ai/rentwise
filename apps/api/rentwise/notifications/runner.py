"""AlertRunner: re-runs a saved search, dispatches alerts for new
listings, records the dedup ledger.

The runner is decoupled from the scheduler so a manual ``/run-now``
endpoint and the scheduler tick share the exact same code path.

Failure modes:

- Aggregator raises → no notification, no dedup row written. Next
  tick will retry naturally.
- Notifier raises → dedup row is **not** written for the listings
  in that dispatch, so the next tick will retry.
- ``alert_enabled=False`` or ``alert_email is None`` → silent skip.
"""

from __future__ import annotations

import json
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
    sent: int
    skipped: bool  # True when alert_enabled / alert_email gates the run
    error: str | None = None


class Aggregator(Protocol):
    """Minimal aggregator surface the runner needs.

    The real :class:`AggregatorService` already exposes ``search`` —
    we declare the protocol locally so tests can substitute a fake
    without dragging the full aggregator into the harness.
    """

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
        notifier: Notifier,
        alert_log: AlertLogRepo,
        config: RunnerConfig | None = None,
    ) -> None:
        self.aggregator = aggregator
        self.notifier = notifier
        self.alert_log = alert_log
        self.config = config or RunnerConfig()

    async def check_one(self, saved: SavedSearch) -> RunResult:
        if not saved.alert_enabled or saved.alert_email is None:
            return RunResult(cache_key=saved.cache_key, new_listings=0, sent=0, skipped=True)

        query = NormalizedQuery.model_validate_json(saved.query_json)
        # ``force_refresh`` would be too aggressive — the cache TTL on
        # the aggregator already handles re-fetch. We just want the
        # current result set.
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

        already_alerted = await self.alert_log.get_alerted_ids(saved.cache_key)
        new_listings = [li for li in resp.listings if str(li.id) not in already_alerted]
        if not new_listings:
            return RunResult(cache_key=saved.cache_key, new_listings=0, sent=0, skipped=False)

        # Cap notifications per dispatch — first-run on a popular saved
        # search shouldn't blast 200 emails. Trim and record only the
        # subset we sent so the rest fall through naturally on the next tick.
        batch = new_listings[: self.config.max_listings_per_email]

        try:
            await self._dispatch(saved, batch)
        except NotifierError as exc:
            log.warning("alert.notifier_failed", cache_key=saved.cache_key, error=str(exc))
            return RunResult(
                cache_key=saved.cache_key,
                new_listings=len(new_listings),
                sent=0,
                skipped=False,
                error=str(exc),
            )

        await self.alert_log.record_alerted(saved.cache_key, [str(li.id) for li in batch])
        log.info(
            "alert.sent",
            cache_key=saved.cache_key,
            sent=len(batch),
            total_new=len(new_listings),
        )
        return RunResult(
            cache_key=saved.cache_key,
            new_listings=len(new_listings),
            sent=len(batch),
            skipped=False,
        )

    async def _dispatch(self, saved: SavedSearch, batch: list[NormalizedListing]) -> None:
        assert saved.alert_email is not None  # narrowed by check_one
        alert = compose_alert(
            label=saved.user_label,
            listings=batch,
            app_base_url=self.config.app_base_url,
            cache_key=saved.cache_key,
            to=saved.alert_email,
        )
        await self.notifier.send_alert(alert)

    async def check_all(self, search_repo: SearchRepo) -> list[RunResult]:
        """Run every alert-enabled saved search once. Used by the scheduler
        tick when running in catch-up mode (rare) and by tests that want
        to fan out without dealing with APScheduler intervals."""
        out: list[RunResult] = []
        for saved in await search_repo.list_saved():
            if not saved.alert_enabled:
                continue
            out.append(await self.check_one(saved))
        return out


# Re-exported for convenience — tests import this directly.
__all__ = ["Aggregator", "AlertRunner", "RunResult", "RunnerConfig"]


# Quiet a lint about unused json import — kept for forward-compat (PR-C
# may serialize alert payloads for web push).
_ = json
