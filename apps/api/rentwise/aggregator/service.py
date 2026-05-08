"""AggregatorService — entry point for /search."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.adapters.base import (
    SourceAdapter,
    project_query_to_capabilities,
)
from rentwise.aggregator.freshness import (
    cache_key as _cache_key,
)
from rentwise.aggregator.freshness import (
    canonical_query_json,
    is_fresh,
)
from rentwise.dedup.service import DedupService
from rentwise.enrichment.service import EnrichmentService
from rentwise.models import (
    AdapterHealth,
    NormalizedListing,
    SchoolCatchments,
    SearchRequest,
    SearchResponse,
    SortOrder,
)
from rentwise.storage.repositories import (
    CachedSearch,
    ListingRepo,
    SearchRepo,
    SourceHealthRepo,
)

log = structlog.get_logger(__name__)


class AggregatorService:
    def __init__(
        self,
        *,
        adapters: list[SourceAdapter],
        session: AsyncSession,
        cache_ttl_seconds: int,
        enrichment: EnrichmentService | None = None,
        dedup: DedupService | None = None,
    ) -> None:
        self.adapters = adapters
        self.session = session
        self.ttl = cache_ttl_seconds
        self.listing_repo = ListingRepo(session)
        self.search_repo = SearchRepo(session)
        self.health_repo = SourceHealthRepo(session)
        # Optional so tests / boot orderings without the geocoder don't
        # have to construct one. None = enrichment is a no-op.
        self.enrichment = enrichment
        # Optional dedup. None = every listing stays self-canonical.
        self.dedup = dedup

    async def search(self, req: SearchRequest) -> SearchResponse:
        key = _cache_key(req.query)
        cached = await self.search_repo.get(key)

        if (
            cached is not None
            and not req.force_refresh
            and is_fresh(cached.last_run_at or "1970-01-01T00:00:00+00:00", self.ttl)
        ):
            ids = cached.listing_ids
            listings = await self.listing_repo.list_by_ids(ids)
            return self._build_response(
                listings=self._sorted_paginated(listings, req),
                total=cached.total_count,
                cache_status="fresh",
                unsupported=[],
            )

        all_listings: list[NormalizedListing] = []
        unsupported: set[str] = set()
        health: dict[str, AdapterHealth] = {}
        any_succeeded = False

        for adapter in self.adapters:
            projected, dropped = project_query_to_capabilities(req.query, adapter.capabilities)
            unsupported.update(dropped)
            try:
                seen: set[str] = set()
                async for raw in adapter.search(projected):
                    if raw.source_listing_id in seen:
                        continue
                    seen.add(raw.source_listing_id)
                    listing = self._raw_to_normalized(raw)
                    if self.enrichment is not None:
                        try:
                            listing = await self.enrichment.enrich(listing)
                        except Exception as exc:
                            # Enrichment must never block ingestion. Log and
                            # let the un-enriched listing through.
                            log.info(
                                "enrichment.unhandled_error",
                                source=adapter.name,
                                error=str(exc),
                            )
                    if self.dedup is not None:
                        try:
                            listing = await self.dedup.assign_canonical(listing)
                        except Exception as exc:
                            # Dedup is best-effort. Failure → listing stays
                            # self-canonical, ingestion continues.
                            log.info(
                                "dedup.unhandled_error",
                                source=adapter.name,
                                error=str(exc),
                            )
                    saved = await self.listing_repo.upsert(listing)
                    all_listings.append(saved)
                await self.health_repo.set(adapter.name, "ok", error=None)
                health[adapter.name] = AdapterHealth(name=adapter.name, status="ok")
                any_succeeded = True
            except Exception as exc:
                log.warning("adapter.failed", adapter=adapter.name, error=str(exc))
                await self.health_repo.set(adapter.name, "degraded", error=str(exc))
                health[adapter.name] = AdapterHealth(
                    name=adapter.name, status="degraded", last_error=str(exc)
                )

        # Apply enrichment-dependent filters AFTER ingestion. These can't be
        # pushed into the adapter URL params because they depend on
        # geocoded coords + lookup tables, so the adapter strips them and
        # we filter the post-enriched rows here.
        all_listings = self._apply_post_filters(all_listings, req.query)
        # The adapter capability check considers these "unsupported", but
        # PR-B handles them at the aggregator layer — peel them out of
        # the response so clients see them as supported.
        unsupported.discard("school_catchment")
        unsupported.discard("transit_max_walk_minutes")

        if any_succeeded:
            await self.search_repo.upsert(
                CachedSearch(
                    cache_key=key,
                    query_json=canonical_query_json(req.query),
                    listing_ids=[str(x.id) for x in all_listings],
                    total_count=len(all_listings),
                )
            )
            await self.session.flush()
            return self._build_response(
                listings=self._sorted_paginated(all_listings, req),
                total=len(all_listings),
                cache_status="miss",
                unsupported=sorted(unsupported),
                health=health,
            )

        # All adapters failed — do not poison the cache.
        # If a stale cache row exists, serve it tagged "stale" with degraded health.
        if cached is not None:
            stale_ids = cached.listing_ids
            stale_listings = await self.listing_repo.list_by_ids(stale_ids)
            return self._build_response(
                listings=self._sorted_paginated(stale_listings, req),
                total=cached.total_count,
                cache_status="stale",
                unsupported=sorted(unsupported),
                health=health,
            )

        # No stale cache either — return empty miss with degraded health.
        return self._build_response(
            listings=[],
            total=0,
            cache_status="miss",
            unsupported=sorted(unsupported),
            health=health,
        )

    def _build_response(
        self,
        *,
        listings: list[NormalizedListing],
        total: int,
        cache_status: Literal["fresh", "stale", "miss"],
        unsupported: list[str],
        health: dict[str, AdapterHealth] | None = None,
    ) -> SearchResponse:
        return SearchResponse(
            listings=listings,
            total=total,
            cache_status=cache_status,
            unsupported_filters=unsupported,
            source_health=health or {},
        )

    @staticmethod
    def _apply_post_filters(
        listings: list[NormalizedListing], query: Any
    ) -> list[NormalizedListing]:
        """Apply enrichment-dependent filters that no adapter can express
        in its URL params.

        - ``school_catchment``: case-insensitive substring match against any
          of the three catchment fields (elementary / middle / secondary).
        - ``transit_max_walk_minutes``: keep only listings with a
          ``nearest_transit`` whose ``walk_minutes`` ≤ the configured max.
          Listings without a transit lookup result are dropped — the user
          asked for "near transit" and we couldn't confirm.
        """
        catchment = getattr(query, "school_catchment", None)
        max_walk = getattr(query, "transit_max_walk_minutes", None)
        if not catchment and max_walk is None:
            return listings

        out: list[NormalizedListing] = []
        catchment_needle = catchment.casefold().strip() if isinstance(catchment, str) else None
        for listing in listings:
            if catchment_needle:
                sc = listing.school_catchments
                hay = " ".join(filter(None, [sc.elementary, sc.middle, sc.secondary])).casefold()
                if catchment_needle not in hay:
                    continue
            if max_walk is not None:
                t = listing.nearest_transit
                if t is None or t.walk_minutes > max_walk:
                    continue
            out.append(listing)
        return out

    def _sorted_paginated(
        self, listings: list[NormalizedListing], req: SearchRequest
    ) -> list[NormalizedListing]:
        def key(x: NormalizedListing) -> Any:
            if req.sort == SortOrder.PRICE_ASC:
                return (x.price_cad if x.price_cad is not None else 1 << 30,)
            if req.sort == SortOrder.PRICE_DESC:
                return (-(x.price_cad if x.price_cad is not None else 0),)
            if req.sort == SortOrder.BEDROOMS:
                return (-(x.bedrooms or 0),)
            return (-(x.posted_at.timestamp()),)

        ordered = sorted(listings, key=key)
        return ordered[req.offset : req.offset + req.limit]

    @staticmethod
    def _raw_to_normalized(raw: Any) -> NormalizedListing:
        new_id = uuid4()
        return NormalizedListing(
            id=new_id,
            canonical_id=new_id,
            source=raw.source,
            source_url=raw.source_url,
            source_listing_id=raw.source_listing_id,
            title=raw.title,
            address=raw.address,
            address_normalized=None,
            lat=raw.lat,
            lon=raw.lon,
            bedrooms=raw.bedrooms,
            bathrooms=raw.bathrooms,
            price_cad=raw.price_cad,
            pets_allowed=raw.pets_allowed,
            furnished=raw.furnished,
            available_date=raw.available_date,
            posted_at=raw.posted_at,
            last_seen_at=datetime.now(UTC),
            photos=raw.photos,
            description_snippet=raw.description_snippet,
            school_catchments=SchoolCatchments(),
            raw_metadata=raw.raw_metadata,
        )
