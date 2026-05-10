"""Streaming /search aggregator (issue #113).

The non-streaming :class:`AggregatorService` (``service.py``) runs
adapters serially against a single shared session and only returns
once everything has drained. This module implements the streaming
counterpart:

- Adapters run in **parallel** via :class:`asyncio.TaskGroup`.
- Each adapter task owns its **own** ``AsyncSession`` — SQLAlchemy
  AsyncSession is not safe for concurrent use, and per-task sessions
  sidestep the cross-task hazard.
- Listings flow through a shared :class:`asyncio.Queue` so the route
  handler can yield NDJSON events to the client incrementally.

Cache writeback (the persistent ``Search`` row) happens once at the
end of the stream on a fresh session.

The legacy non-streaming path stays in ``service.py`` so the
saved-search alert scheduler keeps working unchanged.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
from rentwise.aggregator.service import _catchment_matches, _is_uncalibrated_scaffold
from rentwise.dedup.service import DedupConfig, DedupService
from rentwise.enrichment.geocode import Geocoder
from rentwise.enrichment.neighborhoods import NeighborhoodLookup
from rentwise.enrichment.photo_hash import PhotoHasher
from rentwise.enrichment.service import EnrichmentConfig, EnrichmentService
from rentwise.models import (
    AdapterHealth,
    NormalizedListing,
    SchoolCatchments,
    SearchRequest,
)
from rentwise.storage.repositories import (
    CachedSearch,
    GeocodeCacheRepo,
    ListingRepo,
    PhotoHashCacheRepo,
    SearchRepo,
    SourceHealthRepo,
)

log = structlog.get_logger(__name__)


# Sentinel pushed to the queue when an adapter task finishes (success
# or failure). Carries the per-adapter outcome the route handler needs
# to emit an `adapter_done` event.
class _AdapterDone:
    __slots__ = ("count", "error", "name", "status")

    def __init__(
        self,
        *,
        name: str,
        count: int,
        status: Literal["ok", "degraded", "down"],
        error: str | None,
    ) -> None:
        self.name = name
        self.count = count
        self.status = status
        self.error = error


def _raw_to_normalized(raw: Any) -> NormalizedListing:
    """Promote a RawListing (no canonical_id, no enrichment) to a
    NormalizedListing skeleton. Same logic as
    ``AggregatorService._raw_to_normalized``; duplicated here to keep
    the streaming module self-contained.
    """
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
        neighborhood=None,
        school_catchments=SchoolCatchments(),
        raw_metadata=raw.raw_metadata,
    )


def _listing_passes_post_filters(
    listing: NormalizedListing,
    query: Any,
    *,
    neighborhoods: NeighborhoodLookup,
) -> bool:
    """Mirror of ``_apply_post_filters`` in service.py, applied per-listing.

    For streaming we can't post-filter once at the end (we'd already have
    emitted listings the user shouldn't see), so each listing runs the
    same neighborhood / catchment / transit gates inline before emit.
    """
    catchment = getattr(query, "school_catchment", None)
    max_walk = getattr(query, "transit_max_walk_minutes", None)
    neighborhoods_q = getattr(query, "neighborhoods", None) or []

    if not catchment and max_walk is None and not neighborhoods_q:
        return True

    if neighborhoods_q:
        official = neighborhoods.resolve(neighborhoods_q)
        official_set = {n.casefold() for n in official}
        # Unresolvable names → skip the filter rather than dropping
        # everything (matches service.py semantics).
        if official_set:
            inside = False
            if listing.neighborhood and listing.neighborhood.casefold() in official_set:
                inside = True
            elif listing.lat is not None and listing.lon is not None:
                name = neighborhoods.lookup(listing.lat, listing.lon)
                if name is not None and name.casefold() in official_set:
                    inside = True
            if not inside:
                return False

    if catchment:
        needle = catchment.casefold().strip() if isinstance(catchment, str) else None
        if needle and not _catchment_matches(listing, needle):
            return False

    if max_walk is not None:
        t = listing.nearest_transit
        if t is None or t.walk_minutes > max_walk:
            return False

    return True


async def stream_search(
    *,
    req: SearchRequest,
    adapters: list[SourceAdapter],
    sessionmaker: async_sessionmaker[AsyncSession],
    cache_ttl_seconds: int,
    enrichment_config: EnrichmentConfig,
    dedup_config: DedupConfig,
    geocoder: Geocoder,
    photo_hasher: PhotoHasher,
    neighborhoods: NeighborhoodLookup,
) -> AsyncIterator[dict[str, Any]]:
    """Run a streaming /search and yield NDJSON-ready dict events.

    Event shapes:
        ``{"event": "started", "adapters": [...]}``
        ``{"event": "listing", "data": {NormalizedListing}}``
        ``{"event": "adapter_done", "adapter": str, "count": int,
            "status": "ok"|"degraded"|"down", "error": str|None}``
        ``{"event": "complete", "total": int, "cache_status": str,
            "unsupported_filters": [...], "source_health": {...}}``
    """
    key = _cache_key(req.query)

    # Cache hit short-circuit. Use a single fresh session for the read.
    if not req.force_refresh:
        async with sessionmaker() as session:
            cached = await SearchRepo(session).get(key)
            if cached is not None and is_fresh(
                cached.last_run_at or "1970-01-01T00:00:00+00:00",
                cache_ttl_seconds,
            ):
                listings = await ListingRepo(session).list_by_ids(cached.listing_ids)
                yield {"event": "started", "adapters": [a.name for a in adapters]}
                for listing in listings:
                    yield {
                        "event": "listing",
                        "data": listing.model_dump(mode="json"),
                    }
                yield {
                    "event": "complete",
                    "total": cached.total_count,
                    "cache_status": "fresh",
                    "unsupported_filters": [],
                    "source_health": {},
                }
                return

    # Fresh fetch path. Parallel adapters, per-task sessions.
    yield {"event": "started", "adapters": [a.name for a in adapters]}

    queue: asyncio.Queue[NormalizedListing | _AdapterDone] = asyncio.Queue()
    accumulated: list[NormalizedListing] = []
    health: dict[str, AdapterHealth] = {}
    unsupported: set[str] = set()
    any_succeeded = False

    async def drain_one(adapter: SourceAdapter) -> None:
        """Run one adapter end-to-end on its own session. Push listings
        as they arrive; push a single :class:`_AdapterDone` on exit.
        """
        projected, dropped = project_query_to_capabilities(req.query, adapter.capabilities)
        unsupported.update(dropped)
        yielded = 0
        adapter_error: Exception | None = None

        async with sessionmaker() as session:
            enrichment = EnrichmentService(
                cache_repo=GeocodeCacheRepo(session),
                geocoder=geocoder,
                config=enrichment_config,
                neighborhoods=neighborhoods,
                photo_hasher=photo_hasher,
                photo_hash_cache=PhotoHashCacheRepo(session),
            )
            dedup = DedupService(session, config=dedup_config)
            listing_repo = ListingRepo(session)

            try:
                seen: set[str] = set()
                async for raw in adapter.search(projected):
                    if raw.source_listing_id in seen:
                        continue
                    seen.add(raw.source_listing_id)
                    listing = _raw_to_normalized(raw)
                    try:
                        listing = await enrichment.enrich(listing)
                    except Exception as exc:
                        log.info(
                            "stream.enrichment_unhandled_error",
                            source=adapter.name,
                            error=str(exc),
                        )
                    try:
                        listing = await dedup.assign_canonical(listing)
                    except Exception as exc:
                        log.info(
                            "stream.dedup_unhandled_error",
                            source=adapter.name,
                            error=str(exc),
                        )
                    if not _listing_passes_post_filters(
                        listing, req.query, neighborhoods=neighborhoods
                    ):
                        continue
                    saved = await listing_repo.upsert(listing)
                    yielded += 1
                    await queue.put(saved)
            except Exception as exc:
                adapter_error = exc
                log.warning("stream.adapter_failed", adapter=adapter.name, error=str(exc))

            # Per-adapter commit so a slow source doesn't hold the
            # write lock for the full request (mirror of issue #109).
            commit_failed = False
            try:
                await session.commit()
            except Exception as commit_exc:
                commit_failed = True
                log.warning("stream.commit_failed", adapter=adapter.name, error=str(commit_exc))
                try:
                    await session.rollback()
                except Exception:
                    pass

            # Source-health write on its own commit so /health endpoints
            # see consistent state regardless of the next adapter.
            if adapter_error is not None:
                status: Literal["ok", "degraded", "down"] = "degraded"
                err: str | None = str(adapter_error)
            elif commit_failed:
                status = "degraded"
                err = "commit_failed"
            elif yielded == 0 and _is_uncalibrated_scaffold(adapter):
                status = "degraded"
                err = "scaffold: extractor not yet calibrated against live HTML"
            else:
                status = "ok"
                err = None

            try:
                await SourceHealthRepo(session).set(adapter.name, status, error=err)
                await session.commit()
            except Exception as health_exc:
                log.warning(
                    "stream.health_write_failed",
                    adapter=adapter.name,
                    error=str(health_exc),
                )
                try:
                    await session.rollback()
                except Exception:
                    pass

            health[adapter.name] = AdapterHealth(name=adapter.name, status=status, last_error=err)
            await queue.put(
                _AdapterDone(name=adapter.name, count=yielded, status=status, error=err)
            )

    # Coordinator: spawn adapter tasks, drain the queue while they run,
    # cap waiting on the queue once all tasks are done.
    pending_adapters = len(adapters)

    async def _all_adapters() -> None:
        # Run adapters concurrently. Failures inside one task don't
        # bring the others down; each task swallows its own exception
        # and reports via the queue.
        await asyncio.gather(*[drain_one(a) for a in adapters], return_exceptions=True)

    coordinator = asyncio.create_task(_all_adapters())

    try:
        while pending_adapters > 0:
            try:
                # Cap the wait so we periodically re-check coordinator
                # state — without this, an adapter that hangs forever
                # before pushing _AdapterDone would deadlock the stream.
                item = await asyncio.wait_for(queue.get(), timeout=0.5)
            except TimeoutError:
                if coordinator.done():
                    # Coordinator finished but queue is empty? Drain
                    # whatever's left and break out.
                    while not queue.empty():
                        item = queue.get_nowait()
                        async for ev in _emit(item, accumulated):
                            yield ev
                        if isinstance(item, _AdapterDone):
                            pending_adapters -= 1
                    break
                continue
            async for ev in _emit(item, accumulated):
                yield ev
            if isinstance(item, _AdapterDone):
                pending_adapters -= 1
                if status_ok_or_degraded(item):
                    any_succeeded = any_succeeded or (item.error is None)
    finally:
        if not coordinator.done():
            # Client disconnected mid-stream → cancel adapter tasks.
            coordinator.cancel()
            try:
                await coordinator
            except (asyncio.CancelledError, Exception):
                pass

    # Aggregator-level un-supported filters that are actually handled
    # by post-filters → strip them from the response (mirrors service.py).
    unsupported.discard("school_catchment")
    unsupported.discard("transit_max_walk_minutes")
    unsupported.discard("neighborhoods")

    cache_status: Literal["fresh", "stale", "miss"] = "miss"

    # Cache writeback uses a fresh session so we don't depend on any
    # adapter task's session lifecycle.
    if any_succeeded:
        async with sessionmaker() as session:
            try:
                await SearchRepo(session).upsert(
                    CachedSearch(
                        cache_key=key,
                        query_json=canonical_query_json(req.query),
                        listing_ids=[str(x.id) for x in accumulated],
                        total_count=len(accumulated),
                    )
                )
                await session.commit()
            except Exception as exc:
                log.warning("stream.cache_writeback_failed", error=str(exc))
                try:
                    await session.rollback()
                except Exception:
                    pass

    yield {
        "event": "complete",
        "total": len(accumulated),
        "cache_status": cache_status,
        "unsupported_filters": sorted(unsupported),
        "source_health": {name: h.model_dump(mode="json") for name, h in sorted(health.items())},
    }


async def _emit(
    item: NormalizedListing | _AdapterDone,
    accumulated: list[NormalizedListing],
) -> AsyncIterator[dict[str, Any]]:
    if isinstance(item, _AdapterDone):
        yield {
            "event": "adapter_done",
            "adapter": item.name,
            "count": item.count,
            "status": item.status,
            "error": item.error,
        }
    else:
        accumulated.append(item)
        yield {
            "event": "listing",
            "data": item.model_dump(mode="json"),
        }


def status_ok_or_degraded(d: _AdapterDone) -> bool:
    """Sentinel guard so we can extend statuses without a type-checker fight."""
    return d.status in ("ok", "degraded", "down")
