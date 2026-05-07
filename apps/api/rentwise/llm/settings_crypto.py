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
            '`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` '
            "and add it to your .env."
        )
    return Fernet(raw.encode())


def encrypt_secret(plaintext: str) -> str:
    """Return a Fernet token (urlsafe base64) for the given plaintext."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    """Decrypt a Fernet token; raises `cryptography.fernet.InvalidToken` if corrupt."""
    return _get_fernet().decrypt(token.encode()).decode()
