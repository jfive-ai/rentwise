"""EnrichmentService: ties address normalization + geocoding + (PR-B)
school catchments + transit into one idempotent pass over a
NormalizedListing.

The aggregator calls :meth:`enrich` for each freshly-fetched listing
*before* the upsert, so the row that lands in SQLite already has
``address_normalized`` + (when possible) ``lat`` / ``lon`` +
``school_catchments`` + ``nearest_transit`` populated.

Failure mode: any exception inside enrichment is caught and logged. The
listing flows through with whatever fields could be filled. Enrichment
must never block a search.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog

from rentwise.enrichment.address import normalize_address
from rentwise.enrichment.geocode import GeocodeError, Geocoder
from rentwise.enrichment.neighborhoods import NeighborhoodLookup
from rentwise.enrichment.photo_hash import PhotoHasher
from rentwise.enrichment.school_catchments import SchoolCatchmentLookup
from rentwise.enrichment.transit import TransitLookup
from rentwise.models import NormalizedListing, SchoolCatchments, TransitInfo
from rentwise.storage.repositories import (
    GeocodeCacheEntry,
    GeocodeCacheRepo,
    PhotoHashCacheEntry,
    PhotoHashCacheRepo,
)

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class EnrichmentConfig:
    enabled: bool = True
    cache_ttl_days: int = 30
    # Transient geocoder failures (403, 429, timeouts, network errors) get
    # a much shorter TTL than successes — long enough that one /search
    # doesn't refire 12 doomed HTTP calls for the same blocked UA, but
    # short enough that the next morning's search retries once the
    # upstream issue clears. See issue #114 — Nominatim 403 storm.
    failure_cache_ttl_seconds: int = 3600
    # Hard wall-clock cap on a single geocode call. If the provider
    # hangs past this, we cache the failure and ship the listing without
    # coords — losing enrichment beats blocking the entire search
    # (issue #114 + #113).
    geocode_hard_timeout_seconds: float = 3.0
    provider: str = "nominatim"
    school_catchments_enabled: bool = True
    transit_enabled: bool = True
    neighborhoods_enabled: bool = True
    photo_hash_enabled: bool = True
    photo_hash_cache_ttl_days: int = 90


class EnrichmentService:
    def __init__(
        self,
        *,
        cache_repo: GeocodeCacheRepo,
        geocoder: Geocoder,
        config: EnrichmentConfig | None = None,
        school_catchments: SchoolCatchmentLookup | None = None,
        transit: TransitLookup | None = None,
        neighborhoods: NeighborhoodLookup | None = None,
        photo_hasher: PhotoHasher | None = None,
        photo_hash_cache: PhotoHashCacheRepo | None = None,
    ) -> None:
        self.cache = cache_repo
        self.geocoder = geocoder
        self.config = config or EnrichmentConfig()
        # Construct lookups lazily so callers that don't need them (e.g.
        # legacy tests) can pass None and get the default packaged data.
        # Lookups are pure / idempotent and cheap to keep around — the
        # parsing happens once on init.
        self._schools = (
            school_catchments if school_catchments is not None else SchoolCatchmentLookup()
        )
        self._transit = transit if transit is not None else TransitLookup()
        self._neighborhoods = neighborhoods if neighborhoods is not None else NeighborhoodLookup()
        self._photo_hasher = photo_hasher
        self._photo_cache = photo_hash_cache

    async def enrich(self, listing: NormalizedListing) -> NormalizedListing:
        """Return a copy of ``listing`` with address + geocode + (PR-B)
        catchment + transit fields filled.

        The original is not mutated. If enrichment is disabled or the
        listing has no address, returns the input unchanged.
        """
        if not self.config.enabled:
            return listing
        if listing.address is None or not listing.address.strip():
            return listing

        canonical = normalize_address(listing.address)
        if canonical is None:
            # Couldn't make sense of the raw address; record nothing and let
            # the listing through.
            return listing

        lat = listing.lat
        lon = listing.lon

        if lat is None or lon is None:
            cached = await self.cache.get(canonical)
            if cached is not None and not GeocodeCacheRepo.is_stale(cached):
                lat, lon = cached.lat, cached.lon
            else:
                lat, lon = await self._fetch_and_cache(canonical)

        phash = await self._lookup_phash(listing)

        return listing.model_copy(
            update={
                "address_normalized": canonical,
                "lat": lat,
                "lon": lon,
                "neighborhood": self._lookup_neighborhood(lat, lon),
                "school_catchments": self._lookup_catchments(lat, lon),
                "nearest_transit": self._lookup_transit(lat, lon),
                "phash": phash if phash is not None else listing.phash,
            }
        )

    async def _fetch_and_cache(self, canonical: str) -> tuple[float | None, float | None]:
        """Hit the geocoder, write the result (positive or negative) to cache.

        Failure modes (issue #114):
        - ``GeocodeError`` (403/429/network): cache short-lived failure,
          return None. Without this, every search refires the doomed
          HTTP call for every listing.
        - Hard timeout: same — better to drop enrichment for one search
          than block the entire request on a stuck provider.
        - ``result is None`` (geocoder said "no match"): cache with the
          long success TTL, since "this address doesn't exist" is
          unlikely to change by tomorrow.
        """
        try:
            result = await asyncio.wait_for(
                self.geocoder.geocode(canonical),
                timeout=self.config.geocode_hard_timeout_seconds,
            )
        except TimeoutError:
            log.info("enrichment.geocode_timeout", address=canonical)
            await self._cache_failure(canonical, reason="timeout")
            return (None, None)
        except GeocodeError as exc:
            log.info("enrichment.geocode_failed", address=canonical, error=str(exc))
            await self._cache_failure(canonical, reason=str(exc))
            return (None, None)
        now = datetime.now(UTC)
        await self.cache.upsert(
            GeocodeCacheEntry(
                address_key=canonical,
                lat=result.lat if result else None,
                lon=result.lon if result else None,
                provider=self.config.provider,
                fetched_at=now.isoformat(),
                stale_after=(now + timedelta(days=self.config.cache_ttl_days)).isoformat(),
            )
        )
        if result is None:
            return (None, None)
        return (result.lat, result.lon)

    async def _cache_failure(self, canonical: str, *, reason: str) -> None:
        """Persist a short-lived negative cache row for a transient failure.

        Encodes the failure reason in ``provider`` (e.g. ``nominatim:fail``)
        so future readers can tell "geocoder unreachable" apart from
        "geocoder said no result". The TTL comes from
        ``failure_cache_ttl_seconds`` so we retry quickly after upstream
        recovers.
        """
        now = datetime.now(UTC)
        await self.cache.upsert(
            GeocodeCacheEntry(
                address_key=canonical,
                lat=None,
                lon=None,
                provider=f"{self.config.provider}:fail",
                fetched_at=now.isoformat(),
                stale_after=(
                    now + timedelta(seconds=self.config.failure_cache_ttl_seconds)
                ).isoformat(),
            )
        )
        # Tiny breadcrumb so log readers can correlate "every listing
        # missing coords" with "every address recently 403'd".
        log.info("enrichment.geocode_failure_cached", address=canonical, reason=reason)

    def _lookup_catchments(self, lat: float | None, lon: float | None) -> SchoolCatchments:
        if not self.config.school_catchments_enabled:
            return SchoolCatchments()
        return self._schools.lookup(lat, lon)

    def _lookup_neighborhood(self, lat: float | None, lon: float | None) -> str | None:
        if not self.config.neighborhoods_enabled:
            return None
        return self._neighborhoods.lookup(lat, lon)

    def _lookup_transit(self, lat: float | None, lon: float | None) -> TransitInfo | None:
        if not self.config.transit_enabled:
            return None
        return self._transit.nearest(lat, lon)

    async def _lookup_phash(self, listing: NormalizedListing) -> str | None:
        """Fetch + hash the listing's primary photo, with cache.

        Returns the existing ``listing.phash`` unchanged if hashing is
        disabled, the hasher / cache aren't configured, or the listing
        has no photos.
        """
        if not self.config.photo_hash_enabled:
            return None
        if self._photo_hasher is None or self._photo_cache is None:
            return None
        if not listing.photos:
            return None
        url = str(listing.photos[0])

        cached = await self._photo_cache.get(url)
        if cached is not None and not PhotoHashCacheRepo.is_stale(cached):
            return cached.phash

        try:
            new_hash = await self._photo_hasher.hash_url(url)
        except Exception as exc:
            log.info("enrichment.photo_hash_failed", url=url, error=str(exc))
            return None

        now = datetime.now(UTC)
        await self._photo_cache.upsert(
            PhotoHashCacheEntry(
                url=url,
                phash=new_hash,
                fetched_at=now.isoformat(),
                stale_after=(
                    now + timedelta(days=self.config.photo_hash_cache_ttl_days)
                ).isoformat(),
            )
        )
        return new_hash
