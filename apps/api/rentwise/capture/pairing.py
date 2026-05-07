"""Singleton repo for the capture-pairing shared secret.

The token is generated server-side; the user pastes it into the extension's
options page. Rotation deletes-then-creates so any old token immediately
stops working.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.storage.models import CapturePairingRow


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_token() -> str:
    # 32 bytes of entropy, URL-safe base64 — fits in headers, no escaping.
    return secrets.token_urlsafe(32)


@dataclass(frozen=True)
class CapturePairing:
    token: str
    created_at: str
    rotated_at: str | None


class CapturePairingRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _row(self) -> CapturePairingRow | None:
        return (
            await self.session.execute(select(CapturePairingRow).where(CapturePairingRow.id == 1))
        ).scalar_one_or_none()

    async def get(self) -> CapturePairing | None:
        row = await self._row()
        if row is None:
            return None
        return CapturePairing(token=row.token, created_at=row.created_at, rotated_at=row.rotated_at)

    async def get_or_create(self) -> CapturePairing:
        row = await self._row()
        if row is None:
            row = CapturePairingRow(
                id=1, token=_new_token(), created_at=_now_iso(), rotated_at=None
            )
            self.session.add(row)
            await self.session.flush()
        return CapturePairing(token=row.token, created_at=row.created_at, rotated_at=row.rotated_at)

    async def rotate(self) -> CapturePairing:
        row = await self._row()
        now = _now_iso()
        if row is None:
            row = CapturePairingRow(id=1, token=_new_token(), created_at=now, rotated_at=None)
            self.session.add(row)
        else:
            row.token = _new_token()
            row.rotated_at = now
        await self.session.flush()
        return CapturePairing(token=row.token, created_at=row.created_at, rotated_at=row.rotated_at)
