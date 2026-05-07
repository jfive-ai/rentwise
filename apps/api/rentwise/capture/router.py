"""Capture router — extension capture + pairing endpoints."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.capture.auth import verify_capture_token, verify_local_origin
from rentwise.capture.pairing import CapturePairingRepo
from rentwise.capture.schemas import (
    CaptureHealthPayload,
    CaptureItemError,
    CapturePairResponse,
    CapturePayload,
    CaptureResponse,
)
from rentwise.storage.db import session_dep

log = structlog.get_logger(__name__)


def build_router(api_base_url: str = "http://127.0.0.1:8000") -> APIRouter:
    router = APIRouter(prefix="/capture", tags=["capture"])

    @router.get(
        "/pair",
        response_model=CapturePairResponse,
        dependencies=[Depends(verify_local_origin)],
    )
    async def pair_get(
        session: AsyncSession = Depends(session_dep),
    ) -> CapturePairResponse:
        repo = CapturePairingRepo(session)
        pairing = await repo.get_or_create()
        await session.commit()
        return CapturePairResponse(token=pairing.token, server_url=api_base_url)

    @router.post(
        "/pair/rotate",
        response_model=CapturePairResponse,
        dependencies=[Depends(verify_local_origin)],
    )
    async def pair_rotate(
        session: AsyncSession = Depends(session_dep),
    ) -> CapturePairResponse:
        repo = CapturePairingRepo(session)
        pairing = await repo.rotate()
        await session.commit()
        return CapturePairResponse(token=pairing.token, server_url=api_base_url)

    @router.post(
        "",
        response_model=CaptureResponse,
        dependencies=[Depends(verify_capture_token)],
    )
    async def capture(
        payload: CapturePayload,
        session: AsyncSession = Depends(session_dep),
    ) -> CaptureResponse:
        from rentwise.storage.repositories import ListingRepo

        repo = ListingRepo(session)
        accepted = 0
        errors: list[CaptureItemError] = []
        for idx, item in enumerate(payload.listings):
            try:
                await repo.upsert_by_source_url(
                    source=payload.source,
                    source_listing_id=item.source_listing_id,
                    fields={
                        "source_url": str(item.url),
                        "title": item.title,
                        "price_cad": item.price,
                        "bedrooms": item.bedrooms,
                        "bathrooms": item.bathrooms,
                        "neighborhood": item.neighborhood,
                        "posted_at": item.posted_at,
                        "photos": item.photo_urls,
                        "thumbnail_url": item.thumbnail_url,
                        "description_snippet": item.description_snippet,
                    },
                    capture_method="extension",
                    page_type=item.page_type,
                    captured_at=payload.captured_at,
                )
                accepted += 1
            except Exception as exc:
                log.warning(
                    "capture_row_failed",
                    source=payload.source,
                    source_listing_id=item.source_listing_id,
                    error=str(exc),
                )
                errors.append(CaptureItemError(index=idx, message=str(exc)))

        try:
            await session.commit()
        except Exception as exc:
            await session.rollback()
            raise HTTPException(status_code=503, detail="storage_unavailable") from exc

        return CaptureResponse(
            accepted=accepted,
            skipped_duplicates=0,
            errors=errors,
        )

    @router.post(
        "/health",
        status_code=204,
        dependencies=[Depends(verify_capture_token)],
    )
    async def capture_health(
        payload: CaptureHealthPayload,
        session: AsyncSession = Depends(session_dep),
    ) -> None:
        from rentwise.storage.repositories import SourceHealthRepo

        repo = SourceHealthRepo(session)
        await repo.set(
            source=payload.source,
            status=payload.status,
            error=f"{payload.schema_version}: {payload.reason}",
        )
        try:
            await session.commit()
        except Exception as exc:
            await session.rollback()
            raise HTTPException(status_code=503, detail="storage_unavailable") from exc
        return None

    return router
