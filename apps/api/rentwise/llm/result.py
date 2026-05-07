"""Result type returned by `LLMClient.translate_query`.

Lives in its own module so `client.py` can import it without going through
`rentwise.llm.__init__`, which itself imports `LLMClient` (would be circular).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from rentwise.models import NormalizedQuery


class TranslateQueryResult(BaseModel):
    """Output of `LLMClient.translate_query`. Includes provenance for debugging."""

    query: NormalizedQuery
    unsupported_filters: list[str] = Field(default_factory=list)
    lang_detected: str = Field(description="Either 'en' or 'ko'.")
    model_used: str = Field(description="The actual model that produced the result.")
