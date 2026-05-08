#!/usr/bin/env python3
"""Generate a VAPID keypair for web push notifications (Phase 5 PR-C).

Usage::

    python scripts/gen_vapid.py

Prints two lines that you copy into your .env:

    RENTWISE_VAPID_PUBLIC_KEY=...
    RENTWISE_VAPID_PRIVATE_KEY=...

The keys are URL-safe base64-encoded raw EC P-256 keys (the format
both `pywebpush` and the browser's `applicationServerKey` accept).
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def main() -> None:
    private = ec.generate_private_key(ec.SECP256R1())
    public = private.public_key()

    # Raw 32-byte private scalar.
    priv_bytes = private.private_numbers().private_value.to_bytes(32, "big")

    # Uncompressed EC point: 0x04 || X || Y → 65 bytes.
    pub_bytes = public.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )

    print(f"RENTWISE_VAPID_PRIVATE_KEY={_b64u(priv_bytes)}")
    print(f"RENTWISE_VAPID_PUBLIC_KEY={_b64u(pub_bytes)}")


if __name__ == "__main__":
    main()
