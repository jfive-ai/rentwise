"""AlertRunner tests (Phase 5 PR-B).

Uses a fake aggregator + a fake notifier with the real AlertLogRepo on
an in-memory SQLite. Covers the full happy / dedup / skip / error matrix.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import HttpUrl

from rentwise.models import (
    NormalizedListing,
    NormalizedQuery,
    SchoolCatchments,
    SearchRequest,
    SearchResponse,
)
from rentwise.notifications.email import EmailAlert, NotifierError
from rentwise.notifications.runner import AlertRunner, RunnerConfig
from rentwise.storage.repositories import (
    AlertLogRepo,
    SavedSearch,
)


def _listing(idx: int) -> NormalizedListing:
    nid = UUID(int=idx)
    now = datetime.now(UTC)
    return NormalizedListing(
        id=nid,
        canonical_id=nid,
        source="craigslist",
        source_url=HttpUrl(f"https://example.com/listing/{idx}"),
        source_listing_id=str(idx),
        title=f"Listing {idx}",
        address="1234 W 4th Ave",
        address_normalized=None,
        lat=None,
        lon=None,
        bedrooms=2.0,
        bathrooms=None,
        price_cad=2800 + idx,
        pets_allowed=None,
        furnished=None,
        available_date=None,
        posted_at=now,
        last_seen_at=now,
        photos=[],
        description_snippet=None,
        school_catchments=SchoolCatchments(),
        raw_metadata={},
    )


def _saved(
    *,
    cache_key: str = "k1",
    label: str | None = "Kits 2br",
    alert_enabled: bool = True,
    alert_email: str | None = "me@example.com",
) -> SavedSearch:
    return SavedSearch(
        cache_key=cache_key,
        query_json=json.dumps({"bedrooms_min": 2}),
        user_label=label,
        alert_enabled=alert_enabled,
        alert_email=alert_email,
        alert_cadence_minutes=60,
        last_run_at=datetime.now(UTC).isoformat(),
        total_count=0,
    )


class FakeAggregator:
    def __init__(self, response_listings: list[NormalizedListing]) -> None:
        self._listings = response_listings
        self.calls: list[NormalizedQuery] = []
        self.raises: Exception | None = None

    async def search(self, req: SearchRequest) -> SearchResponse:
        self.calls.append(req.query)
        if self.raises is not None:
            raise self.raises
        return SearchResponse(
            listings=list(self._listings),
            total=len(self._listings),
            cache_status="miss",
            unsupported_filters=[],
            source_health={},
        )


class RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[EmailAlert] = []
        self.raises: Exception | None = None

    async def send_alert(self, alert: EmailAlert) -> None:
        if self.raises is not None:
            raise self.raises
        self.sent.append(alert)


@pytest.fixture
def make_runner(session):
    def factory(
        listings: list[NormalizedListing],
        *,
        max_per_email: int = 25,
    ) -> tuple[AlertRunner, FakeAggregator, RecordingNotifier, AlertLogRepo]:
        agg = FakeAggregator(listings)
        notifier = RecordingNotifier()
        alert_log = AlertLogRepo(session)
        runner = AlertRunner(
            aggregator=agg,
            notifier=notifier,
            alert_log=alert_log,
            config=RunnerConfig(
                app_base_url="https://app.example",
                max_listings_per_email=max_per_email,
            ),
        )
        return runner, agg, notifier, alert_log

    return factory


@pytest.mark.asyncio
async def test_first_run_sends_one_email_with_all_new_matches(make_runner):
    runner, _agg, notifier, alert_log = make_runner([_listing(1), _listing(2)])
    res = await runner.check_one(_saved())
    assert res.skipped is False
    assert res.new_listings == 2
    assert res.sent == 2
    assert len(notifier.sent) == 1  # one batched email, not one per listing
    assert {str(_listing(i).id) for i in (1, 2)} == await alert_log.get_alerted_ids("k1")


@pytest.mark.asyncio
async def test_second_run_with_no_new_listings_sends_zero(make_runner):
    runner, _agg, notifier, _alert = make_runner([_listing(1)])
    await runner.check_one(_saved())  # first run: 1 sent
    res = await runner.check_one(_saved())
    assert res.new_listings == 0
    assert res.sent == 0
    assert len(notifier.sent) == 1  # still just the first email


@pytest.mark.asyncio
async def test_only_new_listings_notify_on_subsequent_run(make_runner):
    """Two listings on first run, three on second: only the new one fires."""
    runner, agg, notifier, _alert = make_runner([_listing(1), _listing(2)])
    await runner.check_one(_saved())
    # Second tick: aggregator has gained listing #3.
    agg._listings = [_listing(1), _listing(2), _listing(3)]  # type: ignore[attr-defined]
    res = await runner.check_one(_saved())
    assert res.new_listings == 1
    assert res.sent == 1
    assert len(notifier.sent) == 2
    # The second email body should mention only listing 3.
    assert "Listing 3" in notifier.sent[1].text_body
    assert "Listing 2" not in notifier.sent[1].text_body


@pytest.mark.asyncio
async def test_alert_disabled_skips_dispatch_and_aggregator(make_runner):
    runner, agg, notifier, _alert = make_runner([_listing(1)])
    res = await runner.check_one(_saved(alert_enabled=False))
    assert res.skipped is True
    assert agg.calls == []  # aggregator not consulted
    assert notifier.sent == []


@pytest.mark.asyncio
async def test_missing_email_skips_dispatch(make_runner):
    runner, agg, notifier, _alert = make_runner([_listing(1)])
    res = await runner.check_one(_saved(alert_email=None))
    assert res.skipped is True
    assert agg.calls == []
    assert notifier.sent == []


@pytest.mark.asyncio
async def test_aggregator_failure_is_caught_and_returned(make_runner):
    runner, agg, notifier, alert_log = make_runner([_listing(1)])
    agg.raises = RuntimeError("source down")
    res = await runner.check_one(_saved())
    assert res.error == "source down"
    assert res.sent == 0
    assert notifier.sent == []
    # No dedup row written → next run will retry.
    assert await alert_log.get_alerted_ids("k1") == set()


@pytest.mark.asyncio
async def test_notifier_failure_does_not_record_dedup(make_runner):
    """Critical correctness: a failed dispatch must not write the dedup row
    or the user silently loses their first alert for those listings."""
    runner, _agg, notifier, alert_log = make_runner([_listing(1)])
    notifier.raises = NotifierError("smtp down")
    res = await runner.check_one(_saved())
    assert res.error == "smtp down"
    assert res.sent == 0
    assert await alert_log.get_alerted_ids("k1") == set()


@pytest.mark.asyncio
async def test_max_listings_per_email_caps_dispatch(make_runner):
    runner, _agg, notifier, alert_log = make_runner(
        [_listing(i) for i in range(1, 11)],
        max_per_email=4,
    )
    res = await runner.check_one(_saved())
    assert res.new_listings == 10
    assert res.sent == 4
    assert len(notifier.sent) == 1
    # Only the first 4 are recorded; the remaining 6 will fire on the next tick.
    assert len(await alert_log.get_alerted_ids("k1")) == 4


@pytest.mark.asyncio
async def test_check_all_iterates_only_alert_enabled_saved(session, make_runner):
    """check_all() walks SearchRepo.list_saved and runs each enabled one."""
    from rentwise.aggregator.freshness import cache_key as compute_key
    from rentwise.storage.repositories import CachedSearch, SearchRepo

    repo = SearchRepo(session)
    q1 = NormalizedQuery(bedrooms_min=2)
    q2 = NormalizedQuery(bedrooms_min=3)
    k1 = compute_key(q1)
    k2 = compute_key(q2)
    await repo.upsert(
        CachedSearch(
            cache_key=k1,
            query_json=q1.model_dump_json(),
            listing_ids=[],
            total_count=0,
            is_saved=False,
        )
    )
    await repo.upsert(
        CachedSearch(
            cache_key=k2,
            query_json=q2.model_dump_json(),
            listing_ids=[],
            total_count=0,
            is_saved=False,
        )
    )
    await repo.save(k1, label="enabled", alert_enabled=True, alert_email="x@x")
    await repo.save(k2, label="disabled", alert_enabled=False)

    runner, _agg, _notifier, _alert = make_runner([_listing(1)])
    out = await runner.check_all(repo)
    assert {r.cache_key for r in out} == {k1}
