"""POST /search router."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.adapters.base import SourceAdapter
from rentwise.aggregator.service import AggregatorService
from rentwise.dedup.service import DedupConfig, DedupService
from rentwise.enrichment.geocode import Geocoder, NominatimGeocoder
from rentwise.enrichment.photo_hash import HttpxPhotoHasher, PhotoHasher
from rentwise.enrichment.service import EnrichmentConfig, EnrichmentService
from rentwise.models import SearchRequest, SearchResponse
from rentwise.settings import settings
from rentwise.storage.db import session_dep
from rentwise.storage.repositories import GeocodeCacheRepo, PhotoHashCacheRepo


@lru_cache(maxsize=1)
def _build_adapters() -> tuple[SourceAdapter, ...]:
    """Build adapter instances once per process so rate-limit state is shared."""
    from rentwise.adapters.craigslist.adapter import CraigslistAdapter

    adapters: list[SourceAdapter] = [
        CraigslistAdapter(
            region=settings.craigslist_region,
            user_agent=settings.user_agent,
        ),
    ]

    if settings.rentwise_padmapper_enabled:
        # Imported lazily so disabled-by-default deployments never pay the
        # Playwright import cost. PadMapper scaffold; see docs/operational-rules.md.
        from rentwise.adapters.padmapper.adapter import PadMapperAdapter

        adapters.append(PadMapperAdapter(user_agent=settings.user_agent))

    return tuple(adapters)


@lru_cache(maxsize=1)
def _build_geocoder() -> Geocoder:
    """Process-wide geocoder so the 1 req/sec throttle is global, not per-request."""
    return NominatimGeocoder(
        base_url=settings.rentwise_nominatim_base_url,
        user_agent=settings.user_agent,
        timeout_seconds=settings.rentwise_geocode_timeout_seconds,
    )


@lru_cache(maxsize=1)
def _build_photo_hasher() -> PhotoHasher:
    """Process-wide photo hasher so its underlying httpx client is reused."""
    return HttpxPhotoHasher(
        user_agent=settings.user_agent,
        timeout_seconds=settings.rentwise_photo_hash_timeout_seconds,
    )


def get_adapters() -> list[SourceAdapter]:
    """Override in tests via app.dependency_overrides[get_adapters]."""
    return list(_build_adapters())


def get_geocoder() -> Geocoder:
    """Override in tests via app.dependency_overrides[get_geocoder]."""
    return _build_geocoder()


def get_photo_hasher() -> PhotoHasher:
    """Override in tests via app.dependency_overrides[get_photo_hasher]."""
    return _build_photo_hasher()


def build_router() -> APIRouter:
    router = APIRouter()

    @router.post("/search", response_model=SearchResponse)
    async def search(
        request: SearchRequest,
        session: AsyncSession = Depends(session_dep),
        adapters: list[SourceAdapter] = Depends(get_adapters),
        geocoder: Geocoder = Depends(get_geocoder),
        photo_hasher: PhotoHasher = Depends(get_photo_hasher),
    ) -> SearchResponse:
        try:
            enrichment = EnrichmentService(
                cache_repo=GeocodeCacheRepo(session),
                geocoder=geocoder,
                config=EnrichmentConfig(
                    enabled=settings.rentwise_geocode_enabled,
                    cache_ttl_days=settings.rentwise_geocode_cache_ttl_days,
                    photo_hash_enabled=settings.rentwise_photo_hash_enabled,
                    photo_hash_cache_ttl_days=settings.rentwise_photo_hash_cache_ttl_days,
                ),
                photo_hasher=photo_hasher,
                photo_hash_cache=PhotoHashCacheRepo(session),
            )
            dedup = DedupService(
                session,
                config=DedupConfig(
                    enabled=settings.rentwise_dedup_enabled,
                    threshold=settings.rentwise_dedup_confidence_threshold,
                ),
            )
            svc = AggregatorService(
                adapters=adapters,
                session=session,
                cache_ttl_seconds=settings.search_cache_ttl_seconds,
                enrichment=enrichment,
                dedup=dedup,
            )
            resp = await svc.search(request)
            await session.commit()
            return resp
        except Exception:
            await session.rollback()
            raise HTTPException(status_code=503, detail="storage_unavailable") from None

    return router
