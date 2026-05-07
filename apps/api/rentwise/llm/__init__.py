"""LLM client + result types."""

from __future__ import annotations

from pydantic import BaseModel, Field

from rentwise.llm.client import LLMClient
from rentwise.llm.errors import LLMError, LLMMalformedResponse, LLMTransportError
from rentwise.models import NormalizedQuery


class TranslateQueryResult(BaseModel):
    """Output of `LLMClient.translate_query`. Includes provenance for debugging."""

    query: NormalizedQuery
    unsupported_filters: list[str] = Field(default_factory=list)
    lang_detected: str = Field(description="Either 'en' or 'ko'.")
    model_used: str = Field(description="The actual model that produced the result.")


__all__ = [
    "LLMClient",
    "LLMError",
    "LLMMalformedResponse",
    "LLMTransportError",
    "TranslateQueryResult",
]
