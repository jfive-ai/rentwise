"""LLM client.

Wraps LiteLLM so the rest of the app doesn't import it directly. Users can
swap the underlying model via env / settings UI without code changes.

See docs/llm-providers.md for the strategy.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import structlog
from litellm import acompletion
from pydantic import SecretStr, ValidationError

from rentwise.llm.errors import LLMMalformedResponse, LLMTransportError
from rentwise.llm.prompts import QUERY_TOOL_SCHEMA, detect_language, render_system_prompt
from rentwise.llm.result import TranslateQueryResult
from rentwise.llm.settings_models import LLMSettings
from rentwise.models import NormalizedQuery
from rentwise.settings import settings

log = structlog.get_logger(__name__)


class LLMClient:
    """Thin wrapper over LiteLLM with a single fallback retry."""

    async def translate_query(
        self,
        user_input: str,
        override: LLMSettings | None = None,
    ) -> TranslateQueryResult:
        """Translate natural-language input into a TranslateQueryResult.

        When `override` is provided (typically the row persisted via the
        Settings UI), its model/key/timeout/base_url take precedence over env
        defaults. Otherwise we read env-based settings — unchanged Phase-2
        behavior. Tries primary first; on transport failure falls back once
        if a fallback model is configured.
        """
        lang = detect_language(user_input)
        today = datetime.now(UTC).date()
        system_prompt = render_system_prompt(lang, today)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]

        attempts: list[tuple[str, SecretStr | None]]
        if override is not None:
            attempts = [(override.primary_model, override.primary_api_key)]
            if override.fallback_model:
                attempts.append((override.fallback_model, override.fallback_api_key))
            timeout = override.timeout_seconds
            custom_base_url = override.custom_base_url
        else:
            attempts = [(settings.rentwise_llm_model, None)]
            if settings.rentwise_llm_fallback_model:
                attempts.append((settings.rentwise_llm_fallback_model, None))
            timeout = settings.rentwise_llm_timeout_seconds
            custom_base_url = None

        last_transport_error: Exception | None = None
        for model, explicit_key in attempts:
            credentials = _resolve_credentials(model, explicit_key)
            if custom_base_url:
                credentials["api_base"] = custom_base_url
            try:
                response = await acompletion(
                    model=model,
                    messages=messages,
                    tools=[QUERY_TOOL_SCHEMA],
                    tool_choice={"type": "function", "function": {"name": "submit_query"}},
                    timeout=timeout,
                    **credentials,
                )
            except Exception as exc:  # LiteLLM raises many exception types; treat all as transport
                log.warning("llm.translate_query.transport_error", model=model, exc_info=exc)
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
        primary_model = settings.rentwise_llm_model
        provider = primary_model.split("/")[0]
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
                    model=primary_model,
                )
                return False


def _resolve_credentials(
    model: str,
    explicit_key: SecretStr | None = None,
) -> dict[str, str]:
    """Return kwargs (api_key, api_base) to pass to acompletion for the given model.

    `explicit_key` (when set) wins — that's the path used when settings come
    from the DB row written by the Settings UI. When no explicit key is
    given, we fall back to the env-based per-provider key lookup. Empty/None
    values are omitted so LiteLLM's own resolution still applies.
    """
    provider = model.split("/")[0]
    out: dict[str, str] = {}
    if explicit_key is not None:
        out["api_key"] = explicit_key.get_secret_value()
        if provider == "ollama":
            out["api_base"] = settings.ollama_base_url
        return out
    match provider:
        case "openrouter" if settings.openrouter_api_key:
            out["api_key"] = settings.openrouter_api_key
        case "anthropic" if settings.anthropic_api_key:
            out["api_key"] = settings.anthropic_api_key
        case "openai" if settings.openai_api_key:
            out["api_key"] = settings.openai_api_key
        case "google" | "gemini" if settings.google_api_key:
            out["api_key"] = settings.google_api_key
        case "ollama":
            out["api_base"] = settings.ollama_base_url
    return out


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
