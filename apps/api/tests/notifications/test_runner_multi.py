"""AlertRunner multi-channel tests (Phase 5 PR-C).

Two notifiers (email + web push) wired in parallel; each maintains its
own dedup ledger via the (cache_key, listing_id, channel) PK.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import HttpUrl

from rentwise.models import (
    NormalizedListing,
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
        price_cad=2800,
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


def _saved() -> SavedSearch:
    return SavedSearch(
        cache_key="k1",
        query_json=json.dumps({"bedrooms_min": 2}),
        user_label="x",
        alert_enabled=True,
        alert_email="me@example.com",
        alert_cadence_minutes=60,
        last_run_at=datetime.now(UTC).isoformat(),
        total_count=0,
    )


class FakeAggregator:
    def __init__(self, listings: list[NormalizedListing]) -> None:
        self._listings = listings

    async def search(self, req: SearchRequest) -> SearchResponse:
        return SearchResponse(
            listings=list(self._listings),
            total=len(self._listings),
            cache_status="miss",
            unsupported_filters=[],
            source_health={},
        )


class Recorder:
    def __init__(self, *, raises: Exception | None = None) -> None:
        self.sent: list[EmailAlert] = []
        self.raises = raises

    async def send_alert(self, alert: EmailAlert) -> None:
        if self.raises is not None:
            raise self.raises
        self.sent.append(alert)


@pytest.fixture
def make_runner(session):
    def factory(*, channels: dict, listings: list[NormalizedListing]) -> AlertRunner:
        return AlertRunner(
            aggregator=FakeAggregator(listings),
            notifiers=channels,
            alert_log=AlertLogRepo(session),
            config=RunnerConfig(app_base_url="https://app.example"),
        )

    return factory


@pytest.mark.asyncio
async def test_both_channels_fire_once_each_on_first_run(make_runner, session):
    email = Recorder()
    push = Recorder()
    runner = make_runner(channels={"email": email, "web_push": push}, listings=[_listing(1)])

    res = await runner.check_one(_saved())
    assert res.sent_by_channel == {"email": 1, "web_push": 1}
    assert len(email.sent) == 1
    assert len(push.sent) == 1

    log = AlertLogRepo(session)
    assert await log.get_alerted_ids("k1", channel="email") == {str(UUID(int=1))}
    assert await log.get_alerted_ids("k1", channel="web_push") == {str(UUID(int=1))}


@pytest.mark.asyncio
async def test_second_run_dedups_each_channel_independently(make_runner):
    email = Recorder()
    push = Recorder()
    runner = make_runner(channels={"email": email, "web_push": push}, listings=[_listing(1)])

    await runner.check_one(_saved())
    res2 = await runner.check_one(_saved())
    assert res2.sent_by_channel == {"email": 0, "web_push": 0}
    assert len(email.sent) == 1
    assert len(push.sent) == 1


@pytest.mark.asyncio
async def test_adding_push_later_fires_for_email_backlog(make_runner, session):
    """First run: only email is configured. Second run: web push is added.
    Web push should fire for every previously-emailed listing because the
    ledger is per-channel."""
    listings = [_listing(1), _listing(2)]
    email = Recorder()
    runner1 = make_runner(channels={"email": email}, listings=listings)
    await runner1.check_one(_saved())
    assert len(email.sent) == 1  # one batched email for two listings

    push = Recorder()
    runner2 = make_runner(channels={"email": email, "web_push": push}, listings=listings)
    res = await runner2.check_one(_saved())
    assert res.sent_by_channel == {"email": 0, "web_push": 2}
    assert len(push.sent) == 1  # one batched push for the same two listings


@pytest.mark.asyncio
async def test_email_failure_does_not_block_push(make_runner, session):
    email = Recorder(raises=NotifierError("smtp down"))
    push = Recorder()
    runner = make_runner(channels={"email": email, "web_push": push}, listings=[_listing(1)])

    res = await runner.check_one(_saved())
    assert res.sent_by_channel == {"email": 0, "web_push": 1}
    assert res.error_by_channel == {"email": "smtp down"}
    # Push still ran + recorded.
    assert await AlertLogRepo(session).get_alerted_ids("k1", channel="web_push") == {
        str(UUID(int=1))
    }
    # Email did not record — the next tick will retry.
    assert await AlertLogRepo(session).get_alerted_ids("k1", channel="email") == set()


@pytest.mark.asyncio
async def test_no_channels_short_circuits_to_skipped(session):
    runner = AlertRunner(
        aggregator=FakeAggregator([_listing(1)]),
        alert_log=AlertLogRepo(session),
    )
    res = await runner.check_one(_saved())
    assert res.skipped is True
    assert res.sent == 0


def test_passing_both_notifier_and_notifiers_is_a_construction_error(session):
    with pytest.raises(ValueError):
        AlertRunner(
            aggregator=FakeAggregator([]),
            alert_log=AlertLogRepo(session),
            notifier=Recorder(),
            notifiers={"web_push": Recorder()},
        )
