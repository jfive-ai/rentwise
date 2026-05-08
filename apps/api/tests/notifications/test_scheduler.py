"""AlertScheduler tests (Phase 5 PR-B).

We never actually fire intervals here — APScheduler's ``add_job`` /
``remove_job`` API is enough to verify registration / unregistration
behavior. The scheduler is started/stopped to exercise the start
guard but no tick coroutine ever runs because intervals are minutes-long.
"""

from __future__ import annotations

import pytest

from rentwise.notifications.scheduler import AlertScheduler


def _factory_returning(coro):
    """A minimal job_factory that ignores the cache_key and returns the
    same coroutine on every call."""

    def make(_key: str):
        return coro

    return make


@pytest.fixture
def noop_coro():
    async def coro() -> None:
        return None

    return coro


def test_register_lists_the_key(noop_coro) -> None:
    s = AlertScheduler(job_factory=_factory_returning(noop_coro))
    s.register(cache_key="k1", cadence_minutes=30)
    assert s.registered_keys() == ["k1"]


def test_register_with_same_key_replaces_existing(noop_coro) -> None:
    s = AlertScheduler(job_factory=_factory_returning(noop_coro))
    s.register(cache_key="k1", cadence_minutes=30)
    s.register(cache_key="k1", cadence_minutes=15)
    keys = s.registered_keys()
    assert keys == ["k1"]
    # Ensure the *trigger* was replaced (not duplicated).
    assert len(s.scheduler.get_jobs()) == 1


def test_unregister_removes_the_key(noop_coro) -> None:
    s = AlertScheduler(job_factory=_factory_returning(noop_coro))
    s.register(cache_key="k1", cadence_minutes=30)
    s.register(cache_key="k2", cadence_minutes=30)
    s.unregister("k1")
    assert s.registered_keys() == ["k2"]


def test_unregister_missing_key_is_noop(noop_coro) -> None:
    s = AlertScheduler(job_factory=_factory_returning(noop_coro))
    s.unregister("never-existed")  # must not raise


@pytest.mark.asyncio
async def test_start_is_idempotent(noop_coro) -> None:
    s = AlertScheduler(job_factory=_factory_returning(noop_coro))
    s.start()
    s.start()  # second call must be a no-op, not raise
    s.shutdown()


def test_shutdown_before_start_is_noop(noop_coro) -> None:
    s = AlertScheduler(job_factory=_factory_returning(noop_coro))
    s.shutdown()  # must not raise
