# Phase 2 Issue #6 — LLM Settings Persistence + Test-Connection Endpoint

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the user's LLM provider configuration (model + API key, optional fallback) so it survives restarts and can be edited at runtime, and provide a connection-test endpoint that validates the credentials without persisting them.

**Architecture:** A single-row `llm_settings` table holds the configuration. API keys are Fernet-encrypted at rest using a key from `RENTWISE_SETTINGS_ENCRYPTION_KEY` (env). A repository layer hides encryption from callers. Three FastAPI endpoints (`GET`, `PUT`, `POST /test`) expose the settings; `GET` masks secrets, `POST /test` does a tiny `litellm.acompletion` call against the supplied (un-persisted) settings.

**Tech Stack:** SQLAlchemy 2.0 async + Alembic + Pydantic v2 + cryptography (Fernet) + LiteLLM. Already-present stack except for `cryptography` (new dependency).

**Issue:** [#6](https://github.com/jfive-ai/rentwise/issues/6). Branch: `feat/phase-2-llm-settings`.

---

## File Structure

| Path | Purpose |
|---|---|
| `apps/api/pyproject.toml` (modify) | Add `cryptography>=44.0` to deps |
| `apps/api/rentwise/settings.py` (modify) | Add `rentwise_settings_encryption_key: str \| None` field |
| `apps/api/rentwise/llm/settings_models.py` (new) | `LLMSettings` (with secrets), `LLMSettingsPublic` (masked) Pydantic models, `LLMSettingsUpdate` (PUT body) |
| `apps/api/rentwise/llm/settings_crypto.py` (new) | `encrypt_secret(plain) -> str`, `decrypt_secret(token) -> str` using Fernet |
| `apps/api/rentwise/storage/models.py` (modify) | Add `LLMSettingsRow` ORM model |
| `apps/api/alembic/versions/0002_llm_settings.py` (new) | Migration creating `llm_settings` table |
| `apps/api/rentwise/storage/llm_settings_repo.py` (new) | `LLMSettingsRepo.get() -> LLMSettings \| None`, `LLMSettingsRepo.upsert(settings) -> LLMSettings` |
| `apps/api/rentwise/main.py` (modify) | `GET /settings/llm`, `PUT /settings/llm`, `POST /settings/llm/test` |
| `apps/api/tests/llm/test_settings_crypto.py` (new) | Encryption round-trip + missing-key behavior |
| `apps/api/tests/storage/test_llm_settings_repo.py` (new) | Repo CRUD, encrypted-at-rest, masking |
| `apps/api/tests/llm/test_settings_endpoints.py` (new) | GET/PUT/POST-test endpoint behavior with TestClient |

---

## Task 1: Dependencies + encryption helper

**Files:**
- Modify: `apps/api/pyproject.toml`
- Modify: `apps/api/rentwise/settings.py`
- Create: `apps/api/rentwise/llm/settings_crypto.py`
- Create: `apps/api/tests/llm/test_settings_crypto.py`

The crypto helper is a thin wrapper around `cryptography.fernet.Fernet` that reads its key from `settings.rentwise_settings_encryption_key`. If the key is missing, it raises `RuntimeError` with a helpful message — we want to fail loudly at first encrypt/decrypt rather than silently storing plaintext.

- [ ] **Step 1: Add `cryptography` to deps**

In `apps/api/pyproject.toml`, add to the `dependencies` list (alphabetically near the top):

```toml
    "cryptography>=44.0",
```

Run `cd apps/api && uv sync` afterwards to refresh the lockfile.

- [ ] **Step 2: Add encryption-key setting**

In `apps/api/rentwise/settings.py`, add a new field to `Settings`:

```python
    # --- Settings encryption ---
    # Fernet key used to encrypt secrets at rest (LLM API keys, etc.).
    # Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
    # Required for any settings persistence; tests provide a fixed key via monkeypatch.
    rentwise_settings_encryption_key: str | None = None
```

(Place it after `rentwise_llm_max_retries` and before the API-key block, with a `--- Settings encryption ---` comment.)

- [ ] **Step 3: Write failing crypto tests**

`apps/api/tests/llm/test_settings_crypto.py`:

```python
"""Encryption helper tests."""

from __future__ import annotations

import pytest

from rentwise.llm.settings_crypto import (
    EncryptionKeyMissingError,
    decrypt_secret,
    encrypt_secret,
)


@pytest.fixture
def fixed_key(monkeypatch: pytest.MonkeyPatch) -> str:
    # Stable Fernet key for test isolation.
    key = "M2zZqQrAvFkkr_xWmaVjJqASfh-dhmL7yLQ2hM6oMmU="
    monkeypatch.setattr(
        "rentwise.llm.settings_crypto.settings.rentwise_settings_encryption_key", key
    )
    return key


def test_encrypt_decrypt_round_trip(fixed_key: str) -> None:
    plaintext = "sk-or-v1-supersecret"
    token = encrypt_secret(plaintext)
    assert token != plaintext
    assert decrypt_secret(token) == plaintext


def test_encrypt_produces_distinct_tokens(fixed_key: str) -> None:
    plaintext = "sk-or-v1-supersecret"
    a = encrypt_secret(plaintext)
    b = encrypt_secret(plaintext)
    # Fernet uses a random IV; identical input → distinct ciphertexts.
    assert a != b
    assert decrypt_secret(a) == plaintext
    assert decrypt_secret(b) == plaintext


def test_encrypt_raises_when_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "rentwise.llm.settings_crypto.settings.rentwise_settings_encryption_key", None
    )
    with pytest.raises(EncryptionKeyMissingError):
        encrypt_secret("anything")


def test_decrypt_raises_when_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "rentwise.llm.settings_crypto.settings.rentwise_settings_encryption_key", None
    )
    with pytest.raises(EncryptionKeyMissingError):
        decrypt_secret("any-token")


def test_decrypt_raises_on_corrupt_token(fixed_key: str) -> None:
    from cryptography.fernet import InvalidToken

    with pytest.raises(InvalidToken):
        decrypt_secret("not-a-real-fernet-token")
```

- [ ] **Step 4: Run; expect ImportError**

Run: `uv run --project /Users/yoonjulee/projects/rentwise/apps/api pytest /Users/yoonjulee/projects/rentwise/.claude/worktrees/draft/apps/api/tests/llm/test_settings_crypto.py -v`
Expected: ImportError.

- [ ] **Step 5: Implement the helper**

`apps/api/rentwise/llm/settings_crypto.py`:

```python
"""Symmetric encryption for secrets stored in the database (e.g. LLM API keys).

Uses Fernet (AES-128-CBC + HMAC-SHA256). The key is read from
`settings.rentwise_settings_encryption_key` on each call so tests can monkeypatch
without re-importing the module.
"""

from __future__ import annotations

from cryptography.fernet import Fernet

from rentwise.settings import settings


class EncryptionKeyMissingError(RuntimeError):
    """Raised when an encrypt/decrypt is attempted without a configured key."""


def _get_fernet() -> Fernet:
    raw = settings.rentwise_settings_encryption_key
    if not raw:
        raise EncryptionKeyMissingError(
            "RENTWISE_SETTINGS_ENCRYPTION_KEY is not set. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"` "
            "and add it to your .env."
        )
    return Fernet(raw.encode())


def encrypt_secret(plaintext: str) -> str:
    """Return a Fernet token (urlsafe base64) for the given plaintext."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    """Decrypt a Fernet token; raises `cryptography.fernet.InvalidToken` if corrupt."""
    return _get_fernet().decrypt(token.encode()).decode()
```

- [ ] **Step 6: Run tests, then commit**

```bash
uv run --project /Users/yoonjulee/projects/rentwise/apps/api pytest /Users/yoonjulee/projects/rentwise/.claude/worktrees/draft/apps/api/tests/llm/test_settings_crypto.py -v
# Expect 5 PASS

git add apps/api/pyproject.toml apps/api/uv.lock apps/api/rentwise/settings.py apps/api/rentwise/llm/settings_crypto.py apps/api/tests/llm/test_settings_crypto.py
git commit -m "feat(api): Fernet-based encryption helper for stored secrets (#6)"
```

---

## Task 2: ORM model + Alembic migration + Pydantic models

**Files:**
- Modify: `apps/api/rentwise/storage/models.py`
- Create: `apps/api/alembic/versions/0002_llm_settings.py`
- Create: `apps/api/rentwise/llm/settings_models.py`

The `llm_settings` table holds exactly one row (enforced by primary key `id=1`). `primary_api_key_encrypted` and `fallback_api_key_encrypted` are TEXT (Fernet tokens are base64). Test connection does NOT touch this table.

- [ ] **Step 1: Add ORM model**

In `apps/api/rentwise/storage/models.py`, after `SourceHealthRow`:

```python
class LLMSettingsRow(Base):
    """Single-row table holding the user's LLM provider configuration.

    The id column is constrained to 1 by the application layer (the repo).
    API keys are Fernet-encrypted at rest.
    """

    __tablename__ = "llm_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    primary_model: Mapped[str] = mapped_column(String, nullable=False)
    primary_api_key_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    fallback_model: Mapped[str | None] = mapped_column(String, nullable=True)
    fallback_api_key_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    custom_base_url: Mapped[str | None] = mapped_column(String, nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
```

- [ ] **Step 2: Add Alembic migration**

`apps/api/alembic/versions/0002_llm_settings.py`:

```python
"""Phase 2 LLM settings table.

Revision ID: 0002_llm_settings
Revises: 0001_initial
Create Date: 2026-05-06
"""

from __future__ import annotations

from alembic import op

revision = "0002_llm_settings"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE llm_settings (
            id                            INTEGER PRIMARY KEY CHECK (id = 1),
            primary_model                 TEXT NOT NULL,
            primary_api_key_encrypted     TEXT,
            fallback_model                TEXT,
            fallback_api_key_encrypted    TEXT,
            custom_base_url               TEXT,
            timeout_seconds               INTEGER NOT NULL DEFAULT 30,
            updated_at                    TEXT NOT NULL
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS llm_settings")
```

- [ ] **Step 3: Add Pydantic models**

`apps/api/rentwise/llm/settings_models.py`:

```python
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
    def from_settings(cls, s: LLMSettings) -> "LLMSettingsPublic":
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
```

- [ ] **Step 4: Verify the migration applies cleanly**

Use the existing `migrated_engine` test fixture (in `apps/api/tests/conftest.py`) — it runs `alembic upgrade head`. We don't need a dedicated test for the migration; it's exercised by every repo test in Task 3.

Quick sanity check now:

```bash
uv run --project /Users/yoonjulee/projects/rentwise/apps/api pytest /Users/yoonjulee/projects/rentwise/.claude/worktrees/draft/apps/api/tests/storage/test_migration.py -v
```

(That existing migration test should still pass with the new revision in place.)

- [ ] **Step 5: Commit**

```bash
git add apps/api/rentwise/storage/models.py apps/api/alembic/versions/0002_llm_settings.py apps/api/rentwise/llm/settings_models.py
git commit -m "feat(api): LLMSettings ORM + Pydantic models + Alembic migration (#6)"
```

---

## Task 3: Repository (encrypt-on-write, decrypt-on-read)

**Files:**
- Create: `apps/api/rentwise/storage/llm_settings_repo.py`
- Create: `apps/api/tests/storage/test_llm_settings_repo.py`

The repo encrypts API keys before SQL and decrypts on read. Callers receive `LLMSettings` (plaintext SecretStr); the on-disk row never contains plaintext.

- [ ] **Step 1: Write failing repo tests**

`apps/api/tests/storage/test_llm_settings_repo.py`:

```python
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
```

- [ ] **Step 2: Run; expect ImportError**

```bash
uv run --project /Users/yoonjulee/projects/rentwise/apps/api pytest /Users/yoonjulee/projects/rentwise/.claude/worktrees/draft/apps/api/tests/storage/test_llm_settings_repo.py -v
```

Expected: ImportError on `rentwise.storage.llm_settings_repo`.

- [ ] **Step 3: Implement the repo**

`apps/api/rentwise/storage/llm_settings_repo.py`:

```python
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
            await self.session.execute(
                select(LLMSettingsRow).where(LLMSettingsRow.id == 1)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return _from_row(row)

    async def upsert(self, settings_in: LLMSettings) -> LLMSettings:
        row = (
            await self.session.execute(
                select(LLMSettingsRow).where(LLMSettingsRow.id == 1)
            )
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
```

- [ ] **Step 4: Run tests**

```bash
uv run --project /Users/yoonjulee/projects/rentwise/apps/api pytest /Users/yoonjulee/projects/rentwise/.claude/worktrees/draft/apps/api/tests/storage/test_llm_settings_repo.py -v
```

Expected: 6 PASS.

- [ ] **Step 5: Run the full storage suite (no regressions)**

```bash
uv run --project /Users/yoonjulee/projects/rentwise/apps/api pytest /Users/yoonjulee/projects/rentwise/.claude/worktrees/draft/apps/api/tests/storage/ -v
```

- [ ] **Step 6: Commit**

```bash
git add apps/api/rentwise/storage/llm_settings_repo.py apps/api/tests/storage/test_llm_settings_repo.py
git commit -m "feat(api): LLMSettingsRepo with encrypt-at-rest and masking (#6)"
```

---

## Task 4: API endpoints — GET / PUT / POST test

**Files:**
- Modify: `apps/api/rentwise/main.py`
- Create: `apps/api/tests/llm/test_settings_endpoints.py`

Mounts three endpoints under `/settings/llm`. The test endpoint NEVER writes to the DB.

- [ ] **Step 1: Write failing endpoint tests**

`apps/api/tests/llm/test_settings_endpoints.py`:

```python
"""Endpoint tests for /settings/llm GET/PUT and /settings/llm/test."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from rentwise.main import app


_TEST_FERNET_KEY = "M2zZqQrAvFkkr_xWmaVjJqASfh-dhmL7yLQ2hM6oMmU="


@pytest.fixture(autouse=True)
def _isolate_db_and_keys(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test gets its own SQLite file + a fresh schema."""
    from alembic import command
    from alembic.config import Config

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setattr("rentwise.settings.settings.database_url", db_url)
    monkeypatch.setattr(
        "rentwise.llm.settings_crypto.settings.rentwise_settings_encryption_key",
        _TEST_FERNET_KEY,
    )
    # Reset cached engine/sessionmaker so they pick up the new URL.
    from rentwise.storage import db as db_mod
    db_mod.get_engine.cache_clear()
    db_mod.get_sessionmaker.cache_clear()

    cfg = Config(
        os.path.join(
            os.path.dirname(__file__), "..", "..", "alembic.ini"
        )
    )
    cfg.set_main_option("sqlalchemy.url", db_url)
    # Apply migrations on a thread (env.py runs asyncio.run internally).
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        loop.run_in_executor = lambda *a, **kw: None  # not used; we just need a sync upgrade
    finally:
        loop.close()
    # Sync upgrade is fine because env.py handles its own loop.
    command.upgrade(cfg, "head")


@pytest.fixture
def http_client() -> TestClient:
    return TestClient(app)


def test_get_returns_404_when_unset(http_client: TestClient) -> None:
    resp = http_client.get("/settings/llm")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "no_llm_settings"


def test_put_creates_settings_then_get_returns_masked(http_client: TestClient) -> None:
    body = {
        "primary_model": "openrouter/qwen/qwen-2.5-72b-instruct:free",
        "primary_api_key": "sk-or-v1-aabbccddeeff",
        "timeout_seconds": 20,
    }
    put = http_client.put("/settings/llm", json=body)
    assert put.status_code == 200, put.text
    payload = put.json()
    assert payload["primary_model"] == body["primary_model"]
    assert payload["primary_api_key_masked"] == "sk-or-...eeff"
    assert "primary_api_key" not in payload  # secret never echoed back

    got = http_client.get("/settings/llm").json()
    assert got["primary_model"] == body["primary_model"]
    assert got["primary_api_key_masked"] == "sk-or-...eeff"
    assert got["timeout_seconds"] == 20


def test_put_validates_required_fields(http_client: TestClient) -> None:
    resp = http_client.put("/settings/llm", json={})
    assert resp.status_code == 422


def test_put_clear_primary_key_via_flag(http_client: TestClient) -> None:
    # Seed
    http_client.put(
        "/settings/llm",
        json={"primary_model": "m", "primary_api_key": "sk-test"},
    )
    # Clear
    resp = http_client.put(
        "/settings/llm",
        json={"primary_model": "m", "primary_api_key_clear": True},
    )
    assert resp.status_code == 200
    assert resp.json()["primary_api_key_masked"] is None


def test_test_connection_success_does_not_persist(
    http_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_response = type(
        "R",
        (),
        {
            "model": "openrouter/qwen/qwen-2.5-72b-instruct:free",
            "choices": [
                type("C", (), {"message": type("M", (), {"content": "ok"})()})()
            ],
        },
    )()
    mock = AsyncMock(return_value=fake_response)
    monkeypatch.setattr("rentwise.main.acompletion", mock)

    body = {
        "primary_model": "openrouter/qwen/qwen-2.5-72b-instruct:free",
        "primary_api_key": "sk-or-v1-test",
        "timeout_seconds": 5,
    }
    resp = http_client.post("/settings/llm/test", json=body)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["ok"] is True
    assert out["error"] is None
    assert out["latency_ms"] >= 0
    assert out["model_used"] == body["primary_model"]
    # And no settings persisted
    get = http_client.get("/settings/llm")
    assert get.status_code == 404


def test_test_connection_failure_returns_ok_false(
    http_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock = AsyncMock(side_effect=RuntimeError("provider unreachable"))
    monkeypatch.setattr("rentwise.main.acompletion", mock)

    body = {
        "primary_model": "openrouter/qwen/qwen-2.5-72b-instruct:free",
        "primary_api_key": "sk-or-v1-test",
    }
    resp = http_client.post("/settings/llm/test", json=body)
    assert resp.status_code == 200
    out = resp.json()
    assert out["ok"] is False
    assert "provider unreachable" in (out["error"] or "")
```

- [ ] **Step 2: Run; expect failures**

```bash
uv run --project /Users/yoonjulee/projects/rentwise/apps/api pytest /Users/yoonjulee/projects/rentwise/.claude/worktrees/draft/apps/api/tests/llm/test_settings_endpoints.py -v
```

- [ ] **Step 3: Implement the endpoints**

In `apps/api/rentwise/main.py`:

Add at top (with other imports):

```python
from time import perf_counter

from fastapi import Depends, HTTPException
from litellm import acompletion
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.llm.settings_models import (
    LLMConnectionTestRequest,
    LLMConnectionTestResult,
    LLMSettings,
    LLMSettingsPublic,
    LLMSettingsUpdate,
)
from rentwise.storage.db import session_dep
from rentwise.storage.llm_settings_repo import LLMSettingsRepo
```

Add inside `create_app()` after the `/translate-query` route:

```python
    @app.get("/settings/llm", response_model=LLMSettingsPublic)
    async def get_llm_settings(
        session: AsyncSession = Depends(session_dep),
    ) -> LLMSettingsPublic:
        repo = LLMSettingsRepo(session)
        current = await repo.get()
        if current is None:
            raise HTTPException(status_code=404, detail="no_llm_settings")
        return LLMSettingsPublic.from_settings(current)

    @app.put("/settings/llm", response_model=LLMSettingsPublic)
    async def put_llm_settings(
        body: LLMSettingsUpdate,
        session: AsyncSession = Depends(session_dep),
    ) -> LLMSettingsPublic:
        repo = LLMSettingsRepo(session)
        existing = await repo.get()

        # Compose new settings, treating omitted SecretStr as "leave unchanged".
        primary_key = body.primary_api_key
        if body.primary_api_key_clear:
            primary_key = None
        elif primary_key is None and existing is not None:
            primary_key = existing.primary_api_key

        fallback_key = body.fallback_api_key
        if body.fallback_api_key_clear:
            fallback_key = None
        elif fallback_key is None and existing is not None:
            fallback_key = existing.fallback_api_key

        new_settings = LLMSettings(
            primary_model=body.primary_model,
            primary_api_key=primary_key,
            fallback_model=body.fallback_model,
            fallback_api_key=fallback_key,
            custom_base_url=body.custom_base_url,
            timeout_seconds=body.timeout_seconds,
        )
        saved = await repo.upsert(new_settings)
        return LLMSettingsPublic.from_settings(saved)

    @app.post("/settings/llm/test", response_model=LLMConnectionTestResult)
    async def test_llm_connection(body: LLMConnectionTestRequest) -> LLMConnectionTestResult:
        """Validate the supplied LLM settings WITHOUT persisting them."""
        kwargs: dict[str, object] = {
            "model": body.primary_model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
            "timeout": body.timeout_seconds,
        }
        if body.primary_api_key is not None:
            kwargs["api_key"] = body.primary_api_key.get_secret_value()
        if body.custom_base_url is not None:
            kwargs["api_base"] = body.custom_base_url

        start = perf_counter()
        try:
            await acompletion(**kwargs)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 — surface any provider error verbatim
            return LLMConnectionTestResult(
                ok=False,
                error=str(exc),
                latency_ms=int((perf_counter() - start) * 1000),
                model_used=body.primary_model,
            )
        return LLMConnectionTestResult(
            ok=True,
            error=None,
            latency_ms=int((perf_counter() - start) * 1000),
            model_used=body.primary_model,
        )
```

- [ ] **Step 4: Run all settings tests**

```bash
uv run --project /Users/yoonjulee/projects/rentwise/apps/api pytest /Users/yoonjulee/projects/rentwise/.claude/worktrees/draft/apps/api/tests/llm/ -v
```

Expected: all green.

- [ ] **Step 5: Run full backend suite — no regressions**

```bash
uv run --project /Users/yoonjulee/projects/rentwise/apps/api pytest /Users/yoonjulee/projects/rentwise/.claude/worktrees/draft/apps/api/tests/ 2>&1 | tail -10
```

- [ ] **Step 6: Lint + format**

```bash
cd /Users/yoonjulee/projects/rentwise/.claude/worktrees/draft/apps/api && ruff check rentwise tests && ruff format --check rentwise tests
```

- [ ] **Step 7: Commit, push, open PR**

```bash
git add apps/api/rentwise/main.py apps/api/tests/llm/test_settings_endpoints.py
git commit -m "feat(api): /settings/llm GET, PUT, /test endpoints (#6)"

git push -u origin feat/phase-2-llm-settings

gh pr create --title "feat(api): LLM settings persistence + /settings/llm endpoints (#6)" --body "$(cat <<'EOF'
Closes #6.

## Summary
- `LLMSettingsRow` SQLAlchemy model + Alembic migration `0002_llm_settings`.
- Fernet encryption-at-rest for API keys (`RENTWISE_SETTINGS_ENCRYPTION_KEY` env).
- `LLMSettingsRepo` with encrypt-on-write / decrypt-on-read.
- `GET /settings/llm` → masked public view (404 when unset).
- `PUT /settings/llm` → upserts, supports leaving keys unchanged or clearing them.
- `POST /settings/llm/test` → tiny `litellm.acompletion` ping with the supplied (un-persisted) settings.

## Test plan
- [x] Crypto round-trip + missing-key behavior
- [x] Repo CRUD + encrypted-at-rest assertion
- [x] Endpoint GET/PUT/POST with mocked litellm
- [x] Full backend suite green
- [x] Lint + format clean

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Also commit this plan file:

```bash
git add docs/superpowers/plans/2026-05-06-phase-2-issue-6-llm-settings.md
git commit -m "docs: add Phase 2 Issue #6 implementation plan"
git push
```

---

## Done checklist (Issue #6)

- [ ] Tasks 1-4 complete with green tests
- [ ] Branch `feat/phase-2-llm-settings` pushed
- [ ] PR opened, links to #6
- [ ] CI green
