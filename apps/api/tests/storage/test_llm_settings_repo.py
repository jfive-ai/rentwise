"""LLMSettingsRepo tests — encryption-at-rest, masking, CRUD."""

from __future__ import annotations

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.llm.settings_models import LLMSettings, LLMSettingsPublic
from rentwise.storage.llm_settings_repo import LLMSettingsRepo
from rentwise.storage.models import LLMSettingsRow

_TEST_FERNET_KEY = "M2zZqQrAvFkkr_xWmaVjJqASfh-dhmL7yLQ2hM6oMmU="


@pytest.fixture(autouse=True)
def _set_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "rentwise.llm.settings_crypto.settings.rentwise_settings_encryption_key",
        _TEST_FERNET_KEY,
    )


async def test_get_returns_none_when_empty(session: AsyncSession) -> None:
    repo = LLMSettingsRepo(session)
    assert await repo.get() is None


async def test_upsert_creates_row(session: AsyncSession) -> None:
    repo = LLMSettingsRepo(session)
    settings_in = LLMSettings(
        primary_model="openrouter/qwen/qwen-2.5-72b-instruct:free",
        primary_api_key=SecretStr("sk-or-v1-test"),
        fallback_model="openrouter/meta-llama/llama-3.3-70b-instruct:free",
        fallback_api_key=SecretStr("sk-or-v1-fb"),
        timeout_seconds=20,
    )
    saved = await repo.upsert(settings_in)
    assert saved.primary_model == settings_in.primary_model
    assert saved.primary_api_key.get_secret_value() == "sk-or-v1-test"
    assert saved.fallback_api_key.get_secret_value() == "sk-or-v1-fb"
    assert saved.timeout_seconds == 20


async def test_upsert_overwrites_existing_row(session: AsyncSession) -> None:
    repo = LLMSettingsRepo(session)
    await repo.upsert(LLMSettings(primary_model="m1", primary_api_key=SecretStr("k1")))
    await repo.upsert(LLMSettings(primary_model="m2", primary_api_key=SecretStr("k2")))
    got = await repo.get()
    assert got is not None
    assert got.primary_model == "m2"
    assert got.primary_api_key.get_secret_value() == "k2"

    # Only one row exists.
    rows = (await session.execute(select(LLMSettingsRow))).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == 1


async def test_keys_are_encrypted_at_rest(session: AsyncSession) -> None:
    plain = "sk-or-v1-secretly-secret"
    repo = LLMSettingsRepo(session)
    await repo.upsert(LLMSettings(primary_model="m", primary_api_key=SecretStr(plain)))

    raw = (await session.execute(select(LLMSettingsRow))).scalars().one()
    assert raw.primary_api_key_encrypted is not None
    assert plain not in raw.primary_api_key_encrypted, (
        "Secret stored in plaintext; expected Fernet token"
    )


async def test_get_returns_none_keys_when_unset(session: AsyncSession) -> None:
    repo = LLMSettingsRepo(session)
    await repo.upsert(LLMSettings(primary_model="ollama/llama3"))  # no key needed
    got = await repo.get()
    assert got is not None
    assert got.primary_api_key is None


def test_public_view_masks_keys() -> None:
    s = LLMSettings(
        primary_model="m",
        primary_api_key=SecretStr("sk-or-v1-aabbccddeeff"),
    )
    public = LLMSettingsPublic.from_settings(s)
    assert public.primary_api_key_masked is not None
    assert "aabbccddeeff" not in public.primary_api_key_masked
    assert public.primary_api_key_masked.startswith("sk-or-")
    assert public.primary_api_key_masked.endswith("eeff")
