"""RentWise API entrypoint.

Phase 0: only health and config endpoints. Real search arrives in Phase 1.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from rentwise.llm import LLMClient
from rentwise.llm.errors import LLMError, LLMMalformedResponse, LLMTransportError
from rentwise.settings import ensure_data_dir, settings

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
    async def translate_query(payload: TranslateQueryRequest) -> dict:
        """Translate natural-language input into a NormalizedQuery."""
        from fastapi import HTTPException

        client = LLMClient()
        try:
            result = await client.translate_query(payload.text)
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

    from rentwise.http.search import build_router

    app.include_router(build_router())

    return app


app = create_app()
