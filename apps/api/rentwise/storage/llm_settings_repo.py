"""Repository for the single-row `llm_settings` table.

Encrypts API keys before write and decrypts on read using the Fernet helper
in `rentwise.llm.settings_crypto`. The on-disk row never contains plaintext.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.llm.settings_crypto import decrypt_secret, encrypt_secret
from rentwise.llm.settings_models import LLMSettings
from rentwise.storage.models import LLMSettingsRow


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _from_row(row: LLMSettingsRow) -> LLMSettings:
    return LLMSettings(
        primary_model=row.primary_model,
        primary_api_key=(
            SecretStr(decrypt_secret(row.primary_api_key_encrypted))
            if row.primary_api_key_encrypted
            else None
        ),
        fallback_model=row.fallback_model,
        fallback_api_key=(
            SecretStr(decrypt_secret(row.fallback_api_key_encrypted))
            if row.fallback_api_key_encrypted
            else None
        ),
        custom_base_url=row.custom_base_url,
        timeout_seconds=row.timeout_seconds,
    )


class LLMSettingsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self) -> LLMSettings | None:
        row = (
            await self.session.execute(select(LLMSettingsRow).where(LLMSettingsRow.id == 1))
        ).scalar_one_or_none()
        if row is None:
            return None
        return _from_row(row)

    async def upsert(self, settings_in: LLMSettings) -> LLMSettings:
        row = (
            await self.session.execute(select(LLMSettingsRow).where(LLMSettingsRow.id == 1))
        ).scalar_one_or_none()

        if row is None:
            row = LLMSettingsRow(id=1, primary_model="", updated_at=_now_iso())
            self.session.add(row)

        row.primary_model = settings_in.primary_model
        row.primary_api_key_encrypted = (
            encrypt_secret(settings_in.primary_api_key.get_secret_value())
            if settings_in.primary_api_key
            else None
        )
        row.fallback_model = settings_in.fallback_model
        row.fallback_api_key_encrypted = (
            encrypt_secret(settings_in.fallback_api_key.get_secret_value())
            if settings_in.fallback_api_key
            else None
        )
        row.custom_base_url = settings_in.custom_base_url
        row.timeout_seconds = settings_in.timeout_seconds
        row.updated_at = _now_iso()
        await self.session.commit()
        return _from_row(row)
