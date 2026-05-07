"""Pydantic models for the LLM settings API.

- `LLMSettings`: full domain object including SecretStr API keys.
- `LLMSettingsPublic`: masked variant for `GET /settings/llm` responses.
- `LLMSettingsUpdate`: payload for `PUT /settings/llm`.
- `LLMConnectionTestRequest`: payload for `POST /settings/llm/test` (settings + an optional key value to test, since keys round-trip masked).
- `LLMConnectionTestResult`: result of `POST /settings/llm/test`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr


def _mask(plain: str | None) -> str | None:
    """Return e.g. 'sk-or-v1...XXX9' for display."""
    if plain is None:
        return None
    if len(plain) <= 8:
        return "***"
    return f"{plain[:6]}...{plain[-4:]}"


class LLMSettings(BaseModel):
    """In-memory representation. API keys are SecretStr until persistence/serialization."""

    primary_model: str
    primary_api_key: SecretStr | None = None
    fallback_model: str | None = None
    fallback_api_key: SecretStr | None = None
    custom_base_url: str | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=600)


class LLMSettingsPublic(BaseModel):
    """Response shape for GET — keys are shown masked."""

    primary_model: str
    primary_api_key_masked: str | None = None
    fallback_model: str | None = None
    fallback_api_key_masked: str | None = None
    custom_base_url: str | None = None
    timeout_seconds: int

    @classmethod
    def from_settings(cls, s: LLMSettings) -> LLMSettingsPublic:
        return cls(
            primary_model=s.primary_model,
            primary_api_key_masked=_mask(
                s.primary_api_key.get_secret_value() if s.primary_api_key else None
            ),
            fallback_model=s.fallback_model,
            fallback_api_key_masked=_mask(
                s.fallback_api_key.get_secret_value() if s.fallback_api_key else None
            ),
            custom_base_url=s.custom_base_url,
            timeout_seconds=s.timeout_seconds,
        )


class LLMSettingsUpdate(BaseModel):
    """PUT body. API keys are plaintext on the wire (HTTPS-only is the user's responsibility);
    `null` for `primary_api_key` means *clear it*; omitting the field means *leave unchanged*.
    """

    primary_model: str
    primary_api_key: SecretStr | None = None
    primary_api_key_clear: bool = False  # set True with primary_api_key=None to remove
    fallback_model: str | None = None
    fallback_api_key: SecretStr | None = None
    fallback_api_key_clear: bool = False
    custom_base_url: str | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=600)


class LLMConnectionTestRequest(BaseModel):
    """Settings to test (un-persisted)."""

    primary_model: str
    primary_api_key: SecretStr | None = None
    custom_base_url: str | None = None
    timeout_seconds: int = Field(default=10, ge=1, le=60)


class LLMConnectionTestResult(BaseModel):
    ok: bool
    error: str | None = None
    latency_ms: int = 0
    model_used: str
