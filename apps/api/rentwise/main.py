"""RentWise API entrypoint.

Phase 0: only health and config endpoints. Real search arrives in Phase 1.
"""

from __future__ import annotations

from time import perf_counter

import structlog
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from litellm import acompletion
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.llm import LLMClient
from rentwise.llm.errors import LLMError, LLMMalformedResponse, LLMTransportError
from rentwise.llm.settings_models import (
    LLMConnectionTestRequest,
    LLMConnectionTestResult,
    LLMSettings,
    LLMSettingsPublic,
    LLMSettingsUpdate,
)
from rentwise.settings import ensure_data_dir, settings
from rentwise.storage.db import session_dep
from rentwise.storage.llm_settings_repo import LLMSettingsRepo

log = structlog.get_logger(__name__)


class TranslateQueryRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)

    @field_validator("text")
    @classmethod
    def _strip_and_check(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("text must not be empty after stripping whitespace")
        return v


def create_app() -> FastAPI:
    ensure_data_dir()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Natural-language rental search across Vancouver platforms.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Registered first so it runs before any other startup hook touches the DB
    # (e.g. _start_scheduler reads SearchRepo.list_saved on a fresh checkout).
    @app.on_event("startup")
    async def _auto_migrate() -> None:
        if not settings.auto_migrate:
            return
        from rentwise.storage.migrate import run_migrations

        await run_migrations()

    @app.get("/")
    async def root() -> dict:
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "status": "ok",
            "docs": "/docs",
        }

    @app.get("/health")
    async def health() -> dict:
        """Liveness probe — is the API process responding?"""
        return {"status": "ok"}

    @app.get("/health/llm")
    async def llm_health() -> dict:
        """Is the configured LLM reachable / does it have a key?"""
        client = LLMClient()
        return {
            "configured": client.is_configured(),
            "primary_model": settings.rentwise_llm_model,
            "fallback_model": settings.rentwise_llm_fallback_model,
        }

    @app.post("/translate-query")
    async def translate_query(
        payload: TranslateQueryRequest,
        session: AsyncSession = Depends(session_dep),
    ) -> dict:
        """Translate natural-language input into a NormalizedQuery.

        Prefer the LLM settings written through `PUT /settings/llm` (Settings
        UI); fall back to env-based defaults when no row has been saved.
        Without this lookup the env values would silently shadow the user's
        chosen provider/key, which is what was happening in production for
        users who had configured a non-default model via the UI.
        """
        repo = LLMSettingsRepo(session)
        override = await repo.get()
        client = LLMClient()
        try:
            result = await client.translate_query(payload.text, override=override)
        except LLMMalformedResponse as exc:
            raise HTTPException(
                status_code=502,
                detail={"error": "llm_malformed_response", "message": str(exc)},
            ) from exc
        except LLMTransportError as exc:
            raise HTTPException(
                status_code=502,
                detail={"error": "llm_transport_error", "message": str(exc)},
            ) from exc
        except LLMError as exc:
            raise HTTPException(
                status_code=502,
                detail={"error": "llm_error", "message": str(exc)},
            ) from exc

        return result.model_dump(mode="json")

    @app.get("/settings/llm", response_model=LLMSettingsPublic)
    async def get_llm_settings(
        session: AsyncSession = Depends(session_dep),
    ) -> LLMSettingsPublic:
        repo = LLMSettingsRepo(session)
        current = await repo.get()
        if current is None:
            raise HTTPException(status_code=404, detail="no_llm_settings")
        return LLMSettingsPublic.from_settings(current)

    @app.put("/settings/llm", response_model=LLMSettingsPublic)
    async def put_llm_settings(
        body: LLMSettingsUpdate,
        session: AsyncSession = Depends(session_dep),
    ) -> LLMSettingsPublic:
        repo = LLMSettingsRepo(session)
        existing = await repo.get()

        # Compose new settings, treating omitted SecretStr as "leave unchanged".
        primary_key = body.primary_api_key
        if body.primary_api_key_clear:
            primary_key = None
        elif primary_key is None and existing is not None:
            primary_key = existing.primary_api_key

        fallback_key = body.fallback_api_key
        if body.fallback_api_key_clear:
            fallback_key = None
        elif fallback_key is None and existing is not None:
            fallback_key = existing.fallback_api_key

        new_settings = LLMSettings(
            primary_model=body.primary_model,
            primary_api_key=primary_key,
            fallback_model=body.fallback_model,
            fallback_api_key=fallback_key,
            custom_base_url=body.custom_base_url,
            timeout_seconds=body.timeout_seconds,
        )
        saved = await repo.upsert(new_settings)
        return LLMSettingsPublic.from_settings(saved)

    @app.post("/settings/llm/test", response_model=LLMConnectionTestResult)
    async def test_llm_connection(
        body: LLMConnectionTestRequest,
        session: AsyncSession = Depends(session_dep),
    ) -> LLMConnectionTestResult:
        """Validate LLM settings WITHOUT persisting them.

        Resolution rules for the API key:
        - If the request supplies `primary_api_key`, use that (the user is
          testing a freshly-typed key before saving).
        - Otherwise, if a settings row exists *and its primary_model matches
          the model being tested*, fall back to the saved key (the user
          revisited Settings, didn't click Replace, and is just re-testing
          what's already saved).
        - Otherwise, send no api_key — LiteLLM will surface the missing-key
          error, which is the truthful result.

        Without this fallback, returning users always saw "api_key must be
        set" because the masked key never round-trips back to the request.
        """
        kwargs: dict[str, object] = {
            "model": body.primary_model,
            "messages": [{"role": "user", "content": "ping"}],
            # Reasoning models (gpt-5.x, o-series) consume max_tokens with
            # internal reasoning before any visible output, so a tiny budget
            # like 1 returns "max_tokens reached" before they finish thinking.
            # 256 is enough for any current reasoning model's ping; trivial
            # for non-reasoning ones. LiteLLM normalizes the param name.
            "max_tokens": 256,
            "timeout": body.timeout_seconds,
        }
        if body.primary_api_key is not None:
            kwargs["api_key"] = body.primary_api_key.get_secret_value()
        else:
            saved = await LLMSettingsRepo(session).get()
            if (
                saved is not None
                and saved.primary_model == body.primary_model
                and saved.primary_api_key is not None
            ):
                kwargs["api_key"] = saved.primary_api_key.get_secret_value()
        if body.custom_base_url is not None:
            kwargs["api_base"] = body.custom_base_url

        start = perf_counter()
        try:
            await acompletion(**kwargs)
        except Exception as exc:
            return LLMConnectionTestResult(
                ok=False,
                error=str(exc),
                latency_ms=int((perf_counter() - start) * 1000),
                model_used=body.primary_model,
            )
        return LLMConnectionTestResult(
            ok=True,
            error=None,
            latency_ms=int((perf_counter() - start) * 1000),
            model_used=body.primary_model,
        )

    from rentwise.http.search import build_router

    app.include_router(build_router())

    from rentwise.http.searches import build_router as build_searches_router

    app.include_router(build_searches_router())

    from rentwise.http.web_push import build_router as build_web_push_router

    app.include_router(build_web_push_router())

    from rentwise.http.map_overlays import build_router as build_map_overlays_router

    app.include_router(build_map_overlays_router())

    # Phase 5 PR-B: alert scheduler. Off by default — tests / CI never
    # start a real interval. Production sets RENTWISE_SCHEDULER_ENABLED=1.
    _wire_alert_scheduler(app)

    @app.on_event("shutdown")
    async def _close_playwright_pool() -> None:
        # The shared Chromium owned by PlaywrightPool needs an explicit
        # shutdown so the OS isn't left with orphaned Chromium processes
        # after uvicorn exits.
        from rentwise.adapters.playwright_pool import PlaywrightPool

        await PlaywrightPool.reset()

    return app


def _wire_alert_scheduler(app: FastAPI) -> None:
    if not settings.rentwise_scheduler_enabled:
        return

    from rentwise.notifications.scheduler import AlertScheduler

    scheduler_holder: dict[str, AlertScheduler] = {}

    from collections.abc import Callable, Coroutine
    from typing import Any

    def job_factory(cache_key: str) -> Callable[[], Coroutine[Any, Any, None]]:
        async def tick() -> None:
            from rentwise.adapters.craigslist.adapter import CraigslistAdapter
            from rentwise.aggregator.service import AggregatorService
            from rentwise.notifications.email import SmtpConfig, SmtpEmailNotifier
            from rentwise.notifications.runner import AlertRunner, RunnerConfig
            from rentwise.storage.db import get_sessionmaker
            from rentwise.storage.repositories import AlertLogRepo, SearchRepo

            sessmaker = get_sessionmaker()
            async with sessmaker() as session:
                saved_list = await SearchRepo(session).list_saved()
                target = next((s for s in saved_list if s.cache_key == cache_key), None)
                if target is None:
                    return
                aggregator = AggregatorService(
                    adapters=[
                        CraigslistAdapter(
                            region=settings.craigslist_region,
                            user_agent=settings.user_agent,
                        ),
                    ],
                    session=session,
                    cache_ttl_seconds=settings.search_cache_ttl_seconds,
                )
                notifier = SmtpEmailNotifier(
                    SmtpConfig(
                        host=settings.rentwise_smtp_host or "localhost",
                        port=settings.rentwise_smtp_port,
                        starttls=settings.rentwise_smtp_starttls,
                        username=settings.rentwise_smtp_username,
                        password=settings.rentwise_smtp_password,
                        from_addr=settings.rentwise_alerts_from,
                    )
                )
                runner = AlertRunner(
                    aggregator=aggregator,
                    notifier=notifier,
                    alert_log=AlertLogRepo(session),
                    config=RunnerConfig(
                        app_base_url=settings.rentwise_alerts_app_base_url,
                    ),
                )
                await runner.check_one(target)
                await session.commit()

        return tick

    @app.on_event("startup")
    async def _start_scheduler() -> None:
        from rentwise.storage.db import get_sessionmaker
        from rentwise.storage.repositories import SearchRepo

        scheduler = AlertScheduler(job_factory=job_factory)
        scheduler.start()
        sessmaker = get_sessionmaker()
        async with sessmaker() as session:
            for saved in await SearchRepo(session).list_saved():
                if saved.alert_enabled and saved.alert_email:
                    scheduler.register(
                        cache_key=saved.cache_key,
                        cadence_minutes=saved.alert_cadence_minutes,
                    )
        scheduler_holder["s"] = scheduler

    @app.on_event("shutdown")
    async def _stop_scheduler() -> None:
        s = scheduler_holder.get("s")
        if s is not None:
            s.shutdown(wait=False)


app = create_app()
