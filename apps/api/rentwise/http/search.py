"""POST /search router."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.adapters.base import SourceAdapter
from rentwise.aggregator.service import AggregatorService
from rentwise.aggregator.streaming import stream_search
from rentwise.dedup.service import DedupConfig, DedupService
from rentwise.enrichment.geocode import Geocoder, NominatimGeocoder
from rentwise.enrichment.neighborhoods import NeighborhoodLookup
from rentwise.enrichment.photo_hash import HttpxPhotoHasher, PhotoHasher
from rentwise.enrichment.service import EnrichmentConfig, EnrichmentService
from rentwise.models import SearchRequest, SearchResponse
from rentwise.settings import settings
from rentwise.storage.db import get_sessionmaker, session_dep
from rentwise.storage.repositories import GeocodeCacheRepo, PhotoHashCacheRepo


@lru_cache(maxsize=1)
def _build_adapters() -> tuple[SourceAdapter, ...]:
    """Build adapter instances once per process so rate-limit state is shared."""
    # Demo mode short-circuits live adapters with fixture-backed ones so the
    # full pipeline (aggregator → enrichment → API → UI) works in sandboxed
    # environments where the live sites are unreachable.
    if settings.rentwise_demo_mode:
        from rentwise.adapters.demo import build_demo_adapters

        return tuple(build_demo_adapters())

    from rentwise.adapters.craigslist.adapter import CraigslistAdapter

    adapters: list[SourceAdapter] = [
        CraigslistAdapter(
            region=settings.craigslist_region,
            user_agent=settings.user_agent,
        ),
    ]

    if settings.rentwise_rentalsca_enabled:
        # Imported lazily so disabled-by-default deployments never pay the
        # Playwright import cost. Rentals.ca scaffold; see
        # docs/operational-rules.md "Source notes — Rentals.ca".
        from rentwise.adapters.rentalsca.adapter import RentalsCaAdapter

        adapters.append(RentalsCaAdapter(user_agent=settings.user_agent))

    if settings.rentwise_padmapper_enabled:
        # Imported lazily so disabled-by-default deployments never pay the
        # Playwright import cost. PadMapper scaffold; see docs/operational-rules.md.
        from rentwise.adapters.padmapper.adapter import PadMapperAdapter

        adapters.append(PadMapperAdapter(user_agent=settings.user_agent))

    # Phase 8 PR-E direct-adapter scaffolds. Each one is disabled by
    # default and only constructed when its env var is True. Imports are
    # inside the conditional so disabled-by-default deployments never pay
    # the Playwright import cost. See docs/operational-rules.md for the
    # per-site TOS reality.
    if settings.rentwise_zumper_enabled:
        from rentwise.adapters.zumper.adapter import ZumperAdapter

        adapters.append(ZumperAdapter(user_agent=settings.user_agent))

    if settings.rentwise_rew_enabled:
        from rentwise.adapters.rew.adapter import RewAdapter

        adapters.append(RewAdapter(user_agent=settings.user_agent))

    if settings.rentwise_livrent_enabled:
        from rentwise.adapters.livrent.adapter import LivRentAdapter

        adapters.append(LivRentAdapter(user_agent=settings.user_agent))

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


@lru_cache(maxsize=1)
def _build_neighborhood_lookup() -> NeighborhoodLookup:
    """Process-wide so the GeoJSON polygon set is parsed only once."""
    return NeighborhoodLookup()


def get_adapters() -> list[SourceAdapter]:
    """Override in tests via app.dependency_overrides[get_adapters]."""
    return list(_build_adapters())


def get_geocoder() -> Geocoder:
    """Override in tests via app.dependency_overrides[get_geocoder]."""
    return _build_geocoder()


def get_photo_hasher() -> PhotoHasher:
    """Override in tests via app.dependency_overrides[get_photo_hasher]."""
    return _build_photo_hasher()


def get_neighborhood_lookup() -> NeighborhoodLookup:
    """Override in tests via app.dependency_overrides[get_neighborhood_lookup]."""
    return _build_neighborhood_lookup()


def build_router() -> APIRouter:
    router = APIRouter()

    @router.post("/search", response_model=SearchResponse)
    async def search(
        request: SearchRequest,
        session: AsyncSession = Depends(session_dep),
        adapters: list[SourceAdapter] = Depends(get_adapters),
        geocoder: Geocoder = Depends(get_geocoder),
        photo_hasher: PhotoHasher = Depends(get_photo_hasher),
        neighborhoods: NeighborhoodLookup = Depends(get_neighborhood_lookup),
    ) -> SearchResponse:
        try:
            enrichment = EnrichmentService(
                cache_repo=GeocodeCacheRepo(session),
                geocoder=geocoder,
                config=EnrichmentConfig(
                    enabled=settings.rentwise_geocode_enabled,
                    cache_ttl_days=settings.rentwise_geocode_cache_ttl_days,
                    failure_cache_ttl_seconds=(settings.rentwise_geocode_failure_cache_ttl_seconds),
                    geocode_hard_timeout_seconds=(settings.rentwise_geocode_hard_timeout_seconds),
                    photo_hash_enabled=settings.rentwise_photo_hash_enabled,
                    photo_hash_cache_ttl_days=settings.rentwise_photo_hash_cache_ttl_days,
                ),
                neighborhoods=neighborhoods,
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
                neighborhood_lookup=neighborhoods,
            )
            resp = await svc.search(request)
            await session.commit()
            return resp
        except Exception:
            await session.rollback()
            raise HTTPException(status_code=503, detail="storage_unavailable") from None

    @router.post("/search/stream")
    async def search_stream(
        request: SearchRequest,
        adapters: list[SourceAdapter] = Depends(get_adapters),
        geocoder: Geocoder = Depends(get_geocoder),
        photo_hasher: PhotoHasher = Depends(get_photo_hasher),
        neighborhoods: NeighborhoodLookup = Depends(get_neighborhood_lookup),
    ) -> StreamingResponse:
        """NDJSON streaming counterpart of POST /search (issue #113).

        Adapters run in parallel; listings stream out as they arrive.
        Each adapter task owns its own AsyncSession (AsyncSession is not
        concurrent-safe), so this endpoint deliberately does NOT depend
        on the request-scoped ``session_dep`` — it grabs a sessionmaker.
        """
        sessionmaker = get_sessionmaker()
        enrichment_config = EnrichmentConfig(
            enabled=settings.rentwise_geocode_enabled,
            cache_ttl_days=settings.rentwise_geocode_cache_ttl_days,
            failure_cache_ttl_seconds=(settings.rentwise_geocode_failure_cache_ttl_seconds),
            geocode_hard_timeout_seconds=(settings.rentwise_geocode_hard_timeout_seconds),
            photo_hash_enabled=settings.rentwise_photo_hash_enabled,
            photo_hash_cache_ttl_days=settings.rentwise_photo_hash_cache_ttl_days,
        )
        dedup_config = DedupConfig(
            enabled=settings.rentwise_dedup_enabled,
            threshold=settings.rentwise_dedup_confidence_threshold,
        )

        async def _ndjson() -> AsyncIterator[bytes]:
            async for ev in stream_search(
                req=request,
                adapters=adapters,
                sessionmaker=sessionmaker,
                cache_ttl_seconds=settings.search_cache_ttl_seconds,
                enrichment_config=enrichment_config,
                dedup_config=dedup_config,
                geocoder=geocoder,
                photo_hasher=photo_hasher,
                neighborhoods=neighborhoods,
            ):
                yield (json.dumps(ev) + "\n").encode("utf-8")

        return StreamingResponse(_ndjson(), media_type="application/x-ndjson")

    return router
