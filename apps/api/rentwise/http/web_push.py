"""Web push subscription endpoints (Phase 5 PR-C).

The web client:
1. Calls ``GET /notifications/web-push/public-key`` to get the VAPID
   public key needed to register a subscription with the browser.
2. Hands the resulting ``PushSubscription.toJSON()`` to
   ``POST /notifications/web-push/subscribe``, optionally tagged with
   the user's ``alert_email`` (the routing key).
3. Calls ``DELETE /notifications/web-push/subscribe/{id}`` to unsub.

The server keeps subscriptions even when ``alert_email`` is omitted —
those rows are anonymous and the runner just won't route to them
until the user updates the row with a saved-search email.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.settings import settings
from rentwise.storage.db import session_dep
from rentwise.storage.repositories import WebPushSubscriptionRepo


class PublicKeyResponse(BaseModel):
    public_key: str


class SubscribeKeys(BaseModel):
    p256dh: str = Field(min_length=1)
    auth: str = Field(min_length=1)


class SubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2000)
    keys: SubscribeKeys
    alert_email: str | None = Field(default=None, max_length=254)
    label: str | None = Field(default=None, max_length=200)


class SubscribeResponse(BaseModel):
    id: int
    endpoint: str
    alert_email: str | None
    label: str | None


def build_router() -> APIRouter:
    router = APIRouter(prefix="/notifications/web-push", tags=["notifications"])

    @router.get("/public-key", response_model=PublicKeyResponse)
    async def get_public_key() -> PublicKeyResponse:
        if not settings.rentwise_web_push_enabled or settings.rentwise_vapid_public_key is None:
            raise HTTPException(status_code=503, detail="web_push_not_configured")
        return PublicKeyResponse(public_key=settings.rentwise_vapid_public_key)

    @router.post("/subscribe", response_model=SubscribeResponse)
    async def subscribe(
        body: SubscribeRequest,
        session: AsyncSession = Depends(session_dep),
    ) -> SubscribeResponse:
        if not settings.rentwise_web_push_enabled:
            raise HTTPException(status_code=503, detail="web_push_not_configured")
        repo = WebPushSubscriptionRepo(session)
        sub = await repo.upsert(
            endpoint=body.endpoint,
            p256dh=body.keys.p256dh,
            auth=body.keys.auth,
            alert_email=body.alert_email,
            label=body.label,
        )
        await session.commit()
        return SubscribeResponse(
            id=sub.id,
            endpoint=sub.endpoint,
            alert_email=sub.alert_email,
            label=sub.label,
        )

    @router.delete("/subscribe/{sub_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def unsubscribe(
        sub_id: int,
        session: AsyncSession = Depends(session_dep),
    ) -> None:
        repo = WebPushSubscriptionRepo(session)
        ok = await repo.delete(sub_id)
        if not ok:
            raise HTTPException(status_code=404, detail="not_found")
        await session.commit()
        return None

    return router
