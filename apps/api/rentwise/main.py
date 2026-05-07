"""RentWise API entrypoint.

Phase 0: only health and config endpoints. Real search arrives in Phase 1.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rentwise.llm import LLMClient
from rentwise.models import NormalizedQuery
from rentwise.settings import ensure_data_dir, settings

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
            "primary_model": settings.rentwise_llm_model,
            "fallback_model": settings.rentwise_llm_fallback_model,
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

    from rentwise.http.search import build_router

    app.include_router(build_router())

    return app


app = create_app()
