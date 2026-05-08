"""EnrichmentService: ties address normalization + geocoding into one
idempotent pass over a NormalizedListing.

The aggregator calls :meth:`enrich` for each freshly-fetched listing
*before* the upsert, so the row that lands in SQLite already has
``address_normalized`` and (when possible) ``lat`` / ``lon`` populated.

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
from rentwise.models import NormalizedListing
from rentwise.storage.repositories import GeocodeCacheEntry, GeocodeCacheRepo

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class EnrichmentConfig:
    enabled: bool = True
    cache_ttl_days: int = 30
    provider: str = "nominatim"


class EnrichmentService:
    def __init__(
        self,
        *,
        cache_repo: GeocodeCacheRepo,
        geocoder: Geocoder,
        config: EnrichmentConfig | None = None,
    ) -> None:
        self.cache = cache_repo
        self.geocoder = geocoder
        self.config = config or EnrichmentConfig()

    async def enrich(self, listing: NormalizedListing) -> NormalizedListing:
        """Return a copy of ``listing`` with address+geocode fields filled.

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

        # Two early-exit paths:
        #  - the listing already has lat/lon → respect what the source gave us
        #    but still record the canonical key.
        #  - the cache has a fresh entry (hit or negative).
        if listing.lat is not None and listing.lon is not None:
            return listing.model_copy(update={"address_normalized": canonical})

        cached = await self.cache.get(canonical)
        if cached is not None and not GeocodeCacheRepo.is_stale(cached):
            return listing.model_copy(
                update={
                    "address_normalized": canonical,
                    "lat": cached.lat,
                    "lon": cached.lon,
                }
            )

        # Network path. Anything that goes wrong stays in the log; the
        # listing flows through unenriched.
        try:
            result = await self.geocoder.geocode(canonical)
        except GeocodeError as exc:
            log.info("enrichment.geocode_failed", address=canonical, error=str(exc))
            return listing.model_copy(update={"address_normalized": canonical})

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
            return listing.model_copy(update={"address_normalized": canonical})
        return listing.model_copy(
            update={
                "address_normalized": canonical,
                "lat": result.lat,
                "lon": result.lon,
            }
        )
