"""POST /search router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.adapters.base import SourceAdapter
from rentwise.aggregator.service import AggregatorService
from rentwise.models import SearchRequest, SearchResponse
from rentwise.settings import settings
from rentwise.storage.db import session_dep


def get_adapters() -> list[SourceAdapter]:
    """Override in tests via app.dependency_overrides[get_adapters]."""
    from rentwise.adapters.craigslist.adapter import CraigslistAdapter

    return [
        CraigslistAdapter(
            region=settings.craigslist_region,
            user_agent=settings.user_agent,
        )
    ]


def build_router() -> APIRouter:
    router = APIRouter()

    @router.post("/search", response_model=SearchResponse)
    async def search(
        request: SearchRequest,
        session: AsyncSession = Depends(session_dep),
        adapters: list[SourceAdapter] = Depends(get_adapters),
    ) -> SearchResponse:
        try:
            svc = AggregatorService(
                adapters=adapters,
                session=session,
                cache_ttl_seconds=settings.search_cache_ttl_seconds,
            )
            resp = await svc.search(request)
            await session.commit()
            return resp
        except Exception:
            await session.rollback()
            raise HTTPException(status_code=503, detail="storage_unavailable") from None

    return router
