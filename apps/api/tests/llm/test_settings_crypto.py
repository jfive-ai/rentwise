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
