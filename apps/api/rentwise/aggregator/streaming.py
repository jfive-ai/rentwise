"""Streaming /search aggregator (issue #113).

The non-streaming :class:`AggregatorService` (``service.py``) runs
adapters serially against a single shared session and only returns
once everything has drained. This module implements the streaming
counterpart:

- Adapter tasks run in **parallel** via :class:`asyncio.gather` and
  do **pure network fetch** — they push :class:`RawListing` items
  onto a shared queue, with no DB writes of their own.
- A single coordinator session owns enrichment, dedup, listing
  upsert, and the per-adapter ``source_health`` row. Sequencing all
  writes on one session means:
    1. Cross-adapter ``canonical_id`` merging keeps working — when
       two adapters emit the same property, the coordinator's
       :class:`DedupService` sees the first adapter's row already in
       the DB and merges the second into the same canonical cluster.
    2. Concurrent UNIQUE-key writes on ``geocode_cache`` can't race;
       only the coordinator writes to it.
- Listings flow through a shared :class:`asyncio.Queue` so the route
  handler can yield NDJSON events to the client incrementally.
- Nominatim's 1-req/sec global rate limit means parallel enrichment
  across adapters wouldn't help anyway — serial enrichment on the
  coordinator session is fine.

Cache writeback (the persistent ``Search`` row) happens once at the
end of the stream on the coordinator session. If every adapter
failed AND a stale cache row exists, the stream replays the stale
listings tagged ``cache_status="stale"`` — matching the legacy
``/search`` fallback so a transient upstream outage doesn't erase
the user's previous results.

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
from rentwise.quality.flags import build_context as _quality_build_ctx
from rentwise.quality.flags import compute_flags as _quality_compute
from rentwise.scoring.match import explain as _match_explain
from rentwise.scoring.match import score_listing as _match_score
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
                    # Issue #119 — score cached listings on the way out so
                    # the badge appears even on cache hits.
                    breakdown = _match_score(listing, req.query)
                    scored = listing.model_copy(
                        update={
                            "match_score": breakdown.total,
                            "match_explanation": _match_explain(breakdown, req.query),
                        }
                    )
                    yield {
                        "event": "listing",
                        "data": scored.model_dump(mode="json"),
                    }
                yield {
                    "event": "complete",
                    "total": cached.total_count,
                    "cache_status": "fresh",
                    "unsupported_filters": [],
                    "source_health": {},
                }
                return

    # Fresh fetch path. Adapter tasks run in parallel doing **network
    # fetch only** — no DB writes. A single coordinator session owns
    # enrichment, dedup, listing upsert and source-health writes, so:
    #   1. Cross-adapter ``canonical_id`` merging still works (the
    #      coordinator's DedupService sees every adapter's rows).
    #   2. Concurrent geocode_cache UNIQUE writes can't race — only
    #      the coordinator writes to it.
    # Nominatim is already global-rate-limited to 1 req/sec, so
    # parallelizing enrichment across adapters wouldn't help anyway.
    yield {"event": "started", "adapters": [a.name for a in adapters]}

    queue: asyncio.Queue[Any] = asyncio.Queue()
    accumulated: list[NormalizedListing] = []
    health: dict[str, AdapterHealth] = {}
    unsupported: set[str] = set()
    any_succeeded = False

    async def drain_one(adapter: SourceAdapter) -> None:
        """Pure network-fetch loop: push RawListings, then _AdapterDone.

        No DB writes happen here — the coordinator handles enrichment,
        dedup, upsert, and the source-health row.
        """
        projected, dropped = project_query_to_capabilities(req.query, adapter.capabilities)
        unsupported.update(dropped)
        yielded = 0
        adapter_error: Exception | None = None

        try:
            seen: set[str] = set()
            async for raw in adapter.search(projected):
                if raw.source_listing_id in seen:
                    continue
                seen.add(raw.source_listing_id)
                yielded += 1
                await queue.put(raw)
        except Exception as exc:
            adapter_error = exc
            log.warning("stream.adapter_failed", adapter=adapter.name, error=str(exc))

        if adapter_error is not None:
            status: Literal["ok", "degraded", "down"] = "degraded"
            err: str | None = str(adapter_error)
        elif yielded == 0 and _is_uncalibrated_scaffold(adapter):
            status = "degraded"
            err = "scaffold: extractor not yet calibrated against live HTML"
        else:
            status = "ok"
            err = None

        health[adapter.name] = AdapterHealth(name=adapter.name, status=status, last_error=err)
        await queue.put(_AdapterDone(name=adapter.name, count=yielded, status=status, error=err))

    pending_adapters = len(adapters)

    async def _all_adapters() -> None:
        # Run adapters concurrently. Failures inside one task don't
        # bring the others down; each task swallows its own exception
        # and reports via the queue.
        await asyncio.gather(*[drain_one(a) for a in adapters], return_exceptions=True)

    async with sessionmaker() as coord_session:
        coord_enrichment = EnrichmentService(
            cache_repo=GeocodeCacheRepo(coord_session),
            geocoder=geocoder,
            config=enrichment_config,
            neighborhoods=neighborhoods,
            photo_hasher=photo_hasher,
            photo_hash_cache=PhotoHashCacheRepo(coord_session),
        )
        coord_dedup = DedupService(coord_session, config=dedup_config)
        coord_repo = ListingRepo(coord_session)
        coord_health = SourceHealthRepo(coord_session)

        coordinator = asyncio.create_task(_all_adapters())

        async def _handle(item: Any) -> AsyncIterator[dict[str, Any]]:
            """Enrich + dedup + upsert a raw listing, or surface adapter_done."""
            nonlocal any_succeeded
            if isinstance(item, _AdapterDone):
                # Persist source-health on the coordinator session.
                try:
                    await coord_health.set(item.name, item.status, error=item.error)
                    await coord_session.commit()
                except Exception as exc:
                    log.warning(
                        "stream.health_write_failed",
                        adapter=item.name,
                        error=str(exc),
                    )
                    try:
                        await coord_session.rollback()
                    except Exception:
                        pass
                yield {
                    "event": "adapter_done",
                    "adapter": item.name,
                    "count": item.count,
                    "status": item.status,
                    "error": item.error,
                }
                if item.error is None and item.status == "ok":
                    any_succeeded = True
                return

            # RawListing → normalize → enrich → post-filter → dedup → upsert
            raw = item
            listing = _raw_to_normalized(raw)
            try:
                listing = await coord_enrichment.enrich(listing)
            except Exception as exc:
                log.info("stream.enrichment_unhandled_error", error=str(exc))
            if not _listing_passes_post_filters(listing, req.query, neighborhoods=neighborhoods):
                return
            try:
                listing = await coord_dedup.assign_canonical(listing)
            except Exception as exc:
                log.info("stream.dedup_unhandled_error", error=str(exc))
            saved = await coord_repo.upsert(listing)
            # Issue #119 — attach Match Score before yielding so the
            # client can render the badge as listings stream in.
            breakdown = _match_score(saved, req.query)
            saved = saved.model_copy(
                update={
                    "match_score": breakdown.total,
                    "match_explanation": _match_explain(breakdown, req.query),
                }
            )
            # Per-listing commit so a slow source doesn't hold the
            # SQLite write lock for the whole request (#109).
            try:
                await coord_session.commit()
            except Exception as commit_exc:
                log.warning("stream.listing_commit_failed", error=str(commit_exc))
                try:
                    await coord_session.rollback()
                except Exception:
                    pass
            accumulated.append(saved)
            yield {"event": "listing", "data": saved.model_dump(mode="json")}

        try:
            while pending_adapters > 0:
                try:
                    # Cap the wait so we periodically re-check
                    # coordinator state — without this, an adapter
                    # that hangs forever before pushing _AdapterDone
                    # would deadlock the stream.
                    item = await asyncio.wait_for(queue.get(), timeout=0.5)
                except TimeoutError:
                    if coordinator.done():
                        # Coordinator finished but queue is empty? Drain
                        # whatever's left and break out.
                        while not queue.empty():
                            item = queue.get_nowait()
                            async for ev in _handle(item):
                                yield ev
                            if isinstance(item, _AdapterDone):
                                pending_adapters -= 1
                        break
                    continue
                async for ev in _handle(item):
                    yield ev
                if isinstance(item, _AdapterDone):
                    pending_adapters -= 1
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

        if any_succeeded:
            # Cache writeback on the same coordinator session that did
            # the listing upserts — the listings are already committed
            # per-listing above, so this just records the cache row.
            try:
                await SearchRepo(coord_session).upsert(
                    CachedSearch(
                        cache_key=key,
                        query_json=canonical_query_json(req.query),
                        listing_ids=[str(x.id) for x in accumulated],
                        total_count=len(accumulated),
                    )
                )
                await coord_session.commit()
            except Exception as exc:
                log.warning("stream.cache_writeback_failed", error=str(exc))
                try:
                    await coord_session.rollback()
                except Exception:
                    pass
        else:
            # Every adapter failed. If a stale cache row exists, replay
            # it as listing events tagged "stale" so a transient outage
            # doesn't erase the user's previous results (matches the
            # legacy /search fallback — codex review on #113).
            try:
                cached = await SearchRepo(coord_session).get(key)
            except Exception as exc:
                log.warning("stream.stale_lookup_failed", error=str(exc))
                cached = None
            if cached is not None and not accumulated:
                try:
                    stale = await ListingRepo(coord_session).list_by_ids(cached.listing_ids)
                except Exception as exc:
                    log.warning("stream.stale_load_failed", error=str(exc))
                    stale = []
                if stale:
                    cache_status = "stale"
                    for listing in stale:
                        accumulated.append(listing)
                        yield {
                            "event": "listing",
                            "data": listing.model_dump(mode="json"),
                        }

    # Issue #120 — cross-listing quality flags need the whole pool to be
    # known (medians, contact reuse). Compute once here and emit as a
    # finalizer event the client can use to patch listing state.
    if accumulated:
        ctx = _quality_build_ctx(accumulated)
        flags_map = {
            str(listing.id): [f.value for f in _quality_compute(listing, ctx)]
            for listing in accumulated
        }
        # Drop entries with no flags to keep the payload small.
        flags_map = {lid: f for lid, f in flags_map.items() if f}
        if flags_map:
            yield {"event": "quality_flags", "flags": flags_map}

    yield {
        "event": "complete",
        "total": len(accumulated),
        "cache_status": cache_status,
        "unsupported_filters": sorted(unsupported),
        "source_health": {name: h.model_dump(mode="json") for name, h in sorted(health.items())},
    }
