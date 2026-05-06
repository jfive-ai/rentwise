"""LLM client.

Wraps LiteLLM so the rest of the app doesn't import it directly. Users can
swap the underlying model via env / settings UI without code changes.

See docs/llm-providers.md for the strategy.
"""

from __future__ import annotations

import structlog

from rentwise.settings import settings

log = structlog.get_logger(__name__)


class LLMClient:
    """Thin wrapper over LiteLLM with retry + fallback logic.

    Phase 0: structure only — `translate_query` is a stub. The real implementation
    arrives in Phase 2 (Natural Language Layer).
    """

    def __init__(self) -> None:
        self.primary_model = settings.rentwise_llm_model
        self.fallback_model = settings.rentwise_llm_fallback_model
        self.timeout = settings.rentwise_llm_timeout_seconds
        self.max_retries = settings.rentwise_llm_max_retries

    async def translate_query(self, user_input: str) -> dict:
        """Translate natural-language input into a NormalizedQuery dict.

        Returns an empty dict for now — wire up in Phase 2.
        """
        log.info(
            "llm.translate_query.stub",
            model=self.primary_model,
            input_length=len(user_input),
        )
        # TODO Phase 2: call litellm.acompletion with tool-use schema.
        return {}

    def is_configured(self) -> bool:
        """True if at least one provider key is set for the chosen model."""
        provider = self.primary_model.split("/", 1)[0]
        match provider:
            case "openrouter":
                return settings.openrouter_api_key is not None
            case "anthropic":
                return settings.anthropic_api_key is not None
            case "openai":
                return settings.openai_api_key is not None
            case "google" | "gemini":
                return settings.google_api_key is not None
            case "ollama":
                return True  # local; no key needed
            case _:
                return False
