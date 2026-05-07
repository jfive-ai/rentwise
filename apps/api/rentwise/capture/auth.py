"""Auth dependencies for the capture endpoints.

- `verify_capture_token` — extension → /capture, /capture/health.
  Compares `X-RentWise-Token` against the singleton secret with hmac.compare_digest.
- `verify_local_origin` — web app → /capture/pair, /capture/pair/rotate.
  Rejects any Origin that is not localhost / 127.0.0.1 / [::1] (any port).
"""

from __future__ import annotations

import hmac
from urllib.parse import urlparse

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.capture.pairing import CapturePairingRepo
from rentwise.storage.db import session_dep

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


async def verify_capture_token(
    x_rentwise_token: str | None = Header(default=None),
    session: AsyncSession = Depends(session_dep),
) -> None:
    if x_rentwise_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_token")

    repo = CapturePairingRepo(session)
    pairing = await repo.get()
    if pairing is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_paired")

    if not hmac.compare_digest(x_rentwise_token, pairing.token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad_token")


def verify_local_origin(origin: str | None = Header(default=None)) -> None:
    if origin is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="missing_origin")
    parsed = urlparse(origin)
    if parsed.hostname is None or parsed.hostname not in _LOCAL_HOSTS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="non_local_origin")
