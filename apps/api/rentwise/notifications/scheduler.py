"""APScheduler integration for saved-search alerts.

The scheduler is process-local (``AsyncIOScheduler``). On startup we
walk every alert-enabled saved search and register an interval job;
the job's coroutine builds a fresh DB session, constructs the
:class:`AlertRunner`, and calls ``check_one`` for that saved search.

Why per-saved-search jobs (vs one tick that walks them all):
- Each saved search has its own cadence (``alert_cadence_minutes``);
  per-job intervals respect that cleanly.
- A failure on one job doesn't block the others.
- APScheduler's ``replace_existing`` makes re-registration on add /
  edit cheap.

Why in-memory jobstore:
- Saved searches live in the DB already; we re-register on startup.
- No need for SQLAlchemyJobStore complexity.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

log = structlog.get_logger(__name__)


JOB_PREFIX = "rentwise.alert."


class AlertScheduler:
    """Thin wrapper over APScheduler so callers don't have to know about it.

    ``job_factory`` is a callable that takes a ``cache_key`` and returns
    the coroutine to run on each tick. The factory pattern keeps the
    scheduler decoupled from how sessions / repos are constructed.
    """

    def __init__(
        self,
        *,
        job_factory: Callable[[str], Callable[[], Any]],
        scheduler: AsyncIOScheduler | None = None,
    ) -> None:
        self._scheduler = scheduler or AsyncIOScheduler()
        self._job_factory = job_factory
        self._started = False

    @property
    def scheduler(self) -> AsyncIOScheduler:
        return self._scheduler

    def start(self) -> None:
        if self._started:
            return
        self._scheduler.start()
        self._started = True

    def shutdown(self, *, wait: bool = False) -> None:
        if not self._started:
            return
        self._scheduler.shutdown(wait=wait)
        self._started = False

    def register(self, *, cache_key: str, cadence_minutes: int) -> None:
        """Register or replace a per-saved-search interval job.

        ``replace_existing=True`` doesn't work while the scheduler is
        paused (the in-memory jobstore isn't initialized until start),
        so we explicitly remove a previous job by id first.
        """
        self.unregister(cache_key)
        coro = self._job_factory(cache_key)
        self._scheduler.add_job(
            coro,
            trigger=IntervalTrigger(minutes=cadence_minutes),
            id=_job_id(cache_key),
            name=f"alert {cache_key}",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        log.info("scheduler.registered", cache_key=cache_key, cadence_minutes=cadence_minutes)

    def unregister(self, cache_key: str) -> None:
        """Remove a job by cache key. No-op if it doesn't exist."""
        try:
            self._scheduler.remove_job(_job_id(cache_key))
            log.info("scheduler.unregistered", cache_key=cache_key)
        except Exception:
            # APScheduler raises a JobLookupError if the job isn't there;
            # we swallow it because callers shouldn't have to track state.
            pass

    def registered_keys(self) -> list[str]:
        return [
            _key_from_id(job.id)
            for job in self._scheduler.get_jobs()
            if job.id.startswith(JOB_PREFIX)
        ]


def _job_id(cache_key: str) -> str:
    return f"{JOB_PREFIX}{cache_key}"


def _key_from_id(job_id: str) -> str:
    return job_id[len(JOB_PREFIX) :]
