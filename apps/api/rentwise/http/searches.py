"""POST / GET / DELETE /searches — saved-search CRUD (Phase 5 PR-A).

Saves piggyback on the existing search-cache row, so the user must
have run a search at least once for that query before they can save
it. The endpoint derives the ``cache_key`` from the supplied query so
clients never have to track it.

PR-B adds POST /searches/{cache_key}/run-now: triggers the alert
runner synchronously so the user (or a test) can verify alert
dispatch without waiting for the scheduler tick.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.aggregator.freshness import cache_key as compute_cache_key
from rentwise.models import NormalizedQuery
from rentwise.notifications.runner import AlertRunner, RunResult
from rentwise.storage.db import session_dep
from rentwise.storage.repositories import SavedSearch, SearchRepo


class SaveSearchRequest(BaseModel):
    query: NormalizedQuery
    label: str | None = Field(default=None, max_length=200)
    alert_enabled: bool = False
    alert_email: str | None = Field(default=None, max_length=254)
    cadence_minutes: int | None = Field(default=None, ge=15, le=1440)


class SavedSearchResponse(BaseModel):
    cache_key: str
    query: NormalizedQuery
    label: str | None
    alert_enabled: bool
    alert_email: str | None
    cadence_minutes: int
    last_run_at: str
    total_count: int


class SavedSearchListResponse(BaseModel):
    items: list[SavedSearchResponse]


class RunNowResponse(BaseModel):
    cache_key: str
    new_listings: int
    sent: int
    skipped: bool
    error: str | None = None


def _to_response(saved: SavedSearch) -> SavedSearchResponse:
    return SavedSearchResponse(
        cache_key=saved.cache_key,
        query=NormalizedQuery.model_validate_json(saved.query_json),
        label=saved.user_label,
        alert_enabled=saved.alert_enabled,
        alert_email=saved.alert_email,
        cadence_minutes=saved.alert_cadence_minutes,
        last_run_at=saved.last_run_at,
        total_count=saved.total_count,
    )


def _run_result_to_response(r: RunResult) -> RunNowResponse:
    return RunNowResponse(
        cache_key=r.cache_key,
        new_listings=r.new_listings,
        sent=r.sent,
        skipped=r.skipped,
        error=r.error,
    )


def get_alert_runner(session: AsyncSession = Depends(session_dep)) -> AlertRunner:
    """Build a per-request AlertRunner backed by the production stack.

    Tests override this via ``app.dependency_overrides`` to inject a
    fake aggregator + recording notifier without touching SMTP.
    """
    from rentwise.adapters.base import SourceAdapter
    from rentwise.adapters.craigslist.adapter import CraigslistAdapter
    from rentwise.aggregator.service import AggregatorService
    from rentwise.notifications.email import (
        Notifier,
        SmtpConfig,
        SmtpEmailNotifier,
    )
    from rentwise.notifications.runner import RunnerConfig
    from rentwise.notifications.web_push import VapidConfig, WebPushNotifier
    from rentwise.settings import settings
    from rentwise.storage.repositories import AlertLogRepo, WebPushSubscriptionRepo

    adapters: list[SourceAdapter] = [
        CraigslistAdapter(
            region=settings.craigslist_region,
            user_agent=settings.user_agent,
        ),
    ]
    aggregator = AggregatorService(
        adapters=adapters,
        session=session,
        cache_ttl_seconds=settings.search_cache_ttl_seconds,
    )

    channels: dict[str, Notifier] = {
        "email": SmtpEmailNotifier(
            SmtpConfig(
                host=settings.rentwise_smtp_host or "localhost",
                port=settings.rentwise_smtp_port,
                starttls=settings.rentwise_smtp_starttls,
                username=settings.rentwise_smtp_username,
                password=settings.rentwise_smtp_password,
                from_addr=settings.rentwise_alerts_from,
            )
        )
    }
    if (
        settings.rentwise_web_push_enabled
        and settings.rentwise_vapid_private_key is not None
        and settings.rentwise_vapid_public_key is not None
    ):
        channels["web_push"] = WebPushNotifier(
            repo=WebPushSubscriptionRepo(session),
            vapid=VapidConfig(
                public_key=settings.rentwise_vapid_public_key,
                private_key=settings.rentwise_vapid_private_key,
                contact=settings.rentwise_vapid_contact,
            ),
        )

    return AlertRunner(
        aggregator=aggregator,
        notifiers=channels,
        alert_log=AlertLogRepo(session),
        config=RunnerConfig(app_base_url=settings.rentwise_alerts_app_base_url),
    )


def build_router() -> APIRouter:
    router = APIRouter(prefix="/searches", tags=["searches"])

    @router.post("", response_model=SavedSearchResponse)
    async def save_search(
        body: SaveSearchRequest,
        session: AsyncSession = Depends(session_dep),
    ) -> SavedSearchResponse:
        key = compute_cache_key(body.query)
        repo = SearchRepo(session)
        out = await repo.save(
            key,
            label=body.label,
            alert_enabled=body.alert_enabled,
            alert_email=body.alert_email,
            cadence_minutes=body.cadence_minutes,
        )
        if out is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_in_cache",
                    "message": "Run this search at least once before saving it.",
                },
            )
        await session.commit()
        return _to_response(out)

    @router.get("", response_model=SavedSearchListResponse)
    async def list_saved_searches(
        session: AsyncSession = Depends(session_dep),
    ) -> SavedSearchListResponse:
        repo = SearchRepo(session)
        rows = await repo.list_saved()
        return SavedSearchListResponse(items=[_to_response(r) for r in rows])

    @router.delete("/{cache_key}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_saved_search(
        cache_key: str,
        session: AsyncSession = Depends(session_dep),
    ) -> None:
        repo = SearchRepo(session)
        ok = await repo.delete_saved(cache_key)
        if not ok:
            raise HTTPException(status_code=404, detail="not_found")
        await session.commit()
        return None

    @router.post("/{cache_key}/run-now", response_model=RunNowResponse)
    async def run_now(
        cache_key: str,
        session: AsyncSession = Depends(session_dep),
        runner: AlertRunner = Depends(get_alert_runner),
    ) -> RunNowResponse:
        """Trigger the alert runner for a saved search synchronously.

        Lets the user verify alert dispatch end-to-end without waiting
        for the next scheduler tick. Equivalent to one tick of the
        background job for this saved search.
        """
        repo = SearchRepo(session)
        target = next((s for s in await repo.list_saved() if s.cache_key == cache_key), None)
        if target is None:
            raise HTTPException(status_code=404, detail="not_found")

        result = await runner.check_one(target)
        await session.commit()
        return _run_result_to_response(result)

    return router
