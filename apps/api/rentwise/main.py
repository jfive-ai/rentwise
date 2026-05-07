"""RentWise API entrypoint.

Phase 0: only health and config endpoints. Real search arrives in Phase 1.
"""

from __future__ import annotations

from time import perf_counter

import structlog
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from litellm import acompletion
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.llm import LLMClient
from rentwise.llm.settings_models import (
    LLMConnectionTestRequest,
    LLMConnectionTestResult,
    LLMSettings,
    LLMSettingsPublic,
    LLMSettingsUpdate,
)
from rentwise.models import NormalizedQuery
from rentwise.settings import ensure_data_dir, settings
from rentwise.storage.db import session_dep
from rentwise.storage.llm_settings_repo import LLMSettingsRepo

log = structlog.get_logger(__name__)


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
            "primary_model": client.primary_model,
            "fallback_model": client.fallback_model,
        }

    @app.post("/translate-query")
    async def translate_query(payload: dict) -> dict:
        """Translate natural-language input into a NormalizedQuery.

        Phase 0: returns an empty NormalizedQuery. Real implementation in Phase 2.
        """
        text = payload.get("text", "")
        client = LLMClient()
        parsed = await client.translate_query(text)
        return {
            "input": text,
            "parsed": parsed or NormalizedQuery().model_dump(exclude_none=True),
            "note": "Phase 0 stub — LLM translation arrives in Phase 2.",
        }

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
    ) -> LLMConnectionTestResult:
        """Validate the supplied LLM settings WITHOUT persisting them."""
        kwargs: dict[str, object] = {
            "model": body.primary_model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
            "timeout": body.timeout_seconds,
        }
        if body.primary_api_key is not None:
            kwargs["api_key"] = body.primary_api_key.get_secret_value()
        if body.custom_base_url is not None:
            kwargs["api_base"] = body.custom_base_url

        start = perf_counter()
        try:
            await acompletion(**kwargs)  # type: ignore[arg-type]
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

    return app


app = create_app()
