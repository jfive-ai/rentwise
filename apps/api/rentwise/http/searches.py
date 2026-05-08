"""POST / GET / DELETE /searches — saved-search CRUD (Phase 5 PR-A).

Saves piggyback on the existing search-cache row, so the user must
have run a search at least once for that query before they can save
it. The endpoint derives the ``cache_key`` from the supplied query so
clients never have to track it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.aggregator.freshness import cache_key as compute_cache_key
from rentwise.models import NormalizedQuery
from rentwise.storage.db import session_dep
from rentwise.storage.repositories import SavedSearch, SearchRepo


class SaveSearchRequest(BaseModel):
    query: NormalizedQuery
    label: str | None = Field(default=None, max_length=200)
    alert_enabled: bool = False
    alert_email: str | None = Field(default=None, max_length=254)
    cadence_minutes: int | None = Field(default=None, ge=15, le=1440)


class SavedSearchResponse(BaseModel):
    cache_key: str
    query: NormalizedQuery
    label: str | None
    alert_enabled: bool
    alert_email: str | None
    cadence_minutes: int
    last_run_at: str
    total_count: int


class SavedSearchListResponse(BaseModel):
    items: list[SavedSearchResponse]


def _to_response(saved: SavedSearch) -> SavedSearchResponse:
    return SavedSearchResponse(
        cache_key=saved.cache_key,
        query=NormalizedQuery.model_validate_json(saved.query_json),
        label=saved.user_label,
        alert_enabled=saved.alert_enabled,
        alert_email=saved.alert_email,
        cadence_minutes=saved.alert_cadence_minutes,
        last_run_at=saved.last_run_at,
        total_count=saved.total_count,
    )


def build_router() -> APIRouter:
    router = APIRouter(prefix="/searches", tags=["searches"])

    @router.post("", response_model=SavedSearchResponse)
    async def save_search(
        body: SaveSearchRequest,
        session: AsyncSession = Depends(session_dep),
    ) -> SavedSearchResponse:
        key = compute_cache_key(body.query)
        repo = SearchRepo(session)
        out = await repo.save(
            key,
            label=body.label,
            alert_enabled=body.alert_enabled,
            alert_email=body.alert_email,
            cadence_minutes=body.cadence_minutes,
        )
        if out is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "not_in_cache",
                    "message": "Run this search at least once before saving it.",
                },
            )
        await session.commit()
        return _to_response(out)

    @router.get("", response_model=SavedSearchListResponse)
    async def list_saved_searches(
        session: AsyncSession = Depends(session_dep),
    ) -> SavedSearchListResponse:
        repo = SearchRepo(session)
        rows = await repo.list_saved()
        return SavedSearchListResponse(items=[_to_response(r) for r in rows])

    @router.delete("/{cache_key}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_saved_search(
        cache_key: str,
        session: AsyncSession = Depends(session_dep),
    ) -> None:
        repo = SearchRepo(session)
        ok = await repo.delete_saved(cache_key)
        if not ok:
            raise HTTPException(status_code=404, detail="not_found")
        await session.commit()
        return None

    return router
