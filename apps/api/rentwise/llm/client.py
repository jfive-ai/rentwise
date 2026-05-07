"""LLM client.

Wraps LiteLLM so the rest of the app doesn't import it directly. Users can
swap the underlying model via env / settings UI without code changes.

See docs/llm-providers.md for the strategy.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from litellm import acompletion
from pydantic import ValidationError

from rentwise.llm.errors import LLMMalformedResponse, LLMTransportError
from rentwise.llm.prompts import QUERY_TOOL_SCHEMA, detect_language, pick_prompt
from rentwise.llm.result import TranslateQueryResult
from rentwise.models import NormalizedQuery
from rentwise.settings import settings

log = structlog.get_logger(__name__)


class LLMClient:
    """Thin wrapper over LiteLLM with a single fallback retry."""

    def __init__(self) -> None:
        self.primary_model = settings.rentwise_llm_model
        self.fallback_model = settings.rentwise_llm_fallback_model
        self.timeout = settings.rentwise_llm_timeout_seconds

    async def translate_query(self, user_input: str) -> TranslateQueryResult:
        """Translate natural-language input into a TranslateQueryResult.

        Tries primary model first; on transport failure (any exception from
        LiteLLM), retries once with the fallback model if configured. Malformed
        responses (no tool call, bad JSON, fields outside the schema) raise
        immediately — they indicate a model or prompt regression, not a flake.
        """
        lang = detect_language(user_input)
        system_prompt = pick_prompt(lang)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]

        models_to_try: list[str] = [self.primary_model]
        if settings.rentwise_llm_fallback_model:
            models_to_try.append(settings.rentwise_llm_fallback_model)

        last_transport_error: Exception | None = None
        for model in models_to_try:
            try:
                response = await acompletion(
                    model=model,
                    messages=messages,
                    tools=[QUERY_TOOL_SCHEMA],
                    tool_choice={"type": "function", "function": {"name": "submit_query"}},
                    timeout=self.timeout,
                )
            except Exception as exc:  # LiteLLM raises many exception types; treat all as transport
                log.warning("llm.translate_query.transport_error", model=model, error=str(exc))
                last_transport_error = exc
                continue

            query = _parse_tool_call(response)
            return TranslateQueryResult(
                query=query,
                unsupported_filters=[],  # populated server-side by FilterPanel hints in a later issue
                lang_detected=lang,
                model_used=model,
            )

        raise LLMTransportError(
            f"All LLM providers failed; last error: {last_transport_error!r}"
        ) from last_transport_error

    def is_configured(self) -> bool:
        """True if at least one provider key is set for the chosen model."""
        # Model names can be "provider/model" or "provider/org/model" — always use first segment.
        provider = self.primary_model.split("/")[0]
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
                log.warning(
                    "llm.is_configured.unknown_provider",
                    provider=provider,
                    model=self.primary_model,
                )
                return False


def _parse_tool_call(response: Any) -> NormalizedQuery:
    try:
        choice = response.choices[0]
        tool_calls = getattr(choice.message, "tool_calls", None) or []
        if not tool_calls:
            raise LLMMalformedResponse("LLM returned no tool call")
        fn = tool_calls[0].function
        if fn.name != "submit_query":
            raise LLMMalformedResponse(f"Unexpected tool call: {fn.name}")
        try:
            args: dict[str, Any] = json.loads(fn.arguments)
        except (TypeError, ValueError) as exc:
            raise LLMMalformedResponse(f"Tool arguments not valid JSON: {exc}") from exc
    except LLMMalformedResponse:
        raise
    except Exception as exc:  # response shape we didn't expect
        raise LLMMalformedResponse(f"Unparseable LLM response: {exc!r}") from exc

    # Strict: any extra field means the model violated the schema.
    extra = set(args.keys()) - set(NormalizedQuery.model_fields.keys())
    if extra:
        raise LLMMalformedResponse(f"LLM returned unknown fields: {sorted(extra)}")

    try:
        return NormalizedQuery.model_validate(args)
    except ValidationError as exc:
        raise LLMMalformedResponse(f"Tool arguments failed validation: {exc.errors()}") from exc
