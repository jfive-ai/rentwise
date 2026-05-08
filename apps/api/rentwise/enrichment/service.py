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

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog

from rentwise.enrichment.address import normalize_address
from rentwise.enrichment.geocode import GeocodeError, Geocoder
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
    provider: str = "nominatim"
    school_catchments_enabled: bool = True
    transit_enabled: bool = True
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
                "school_catchments": self._lookup_catchments(lat, lon),
                "nearest_transit": self._lookup_transit(lat, lon),
                "phash": phash if phash is not None else listing.phash,
            }
        )

    async def _fetch_and_cache(self, canonical: str) -> tuple[float | None, float | None]:
        """Hit the geocoder, write the result (positive or negative) to cache."""
        try:
            result = await self.geocoder.geocode(canonical)
        except GeocodeError as exc:
            log.info("enrichment.geocode_failed", address=canonical, error=str(exc))
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

    def _lookup_catchments(self, lat: float | None, lon: float | None) -> SchoolCatchments:
        if not self.config.school_catchments_enabled:
            return SchoolCatchments()
        return self._schools.lookup(lat, lon)

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
