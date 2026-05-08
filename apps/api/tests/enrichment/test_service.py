"""EnrichmentService tests — uses the real cache repo on an in-memory DB
and a fake Geocoder so no live HTTP is needed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import HttpUrl

from rentwise.enrichment.geocode import GeocodeError, GeocodeResult
from rentwise.enrichment.service import EnrichmentConfig, EnrichmentService
from rentwise.models import NormalizedListing, SchoolCatchments
from rentwise.storage.repositories import GeocodeCacheEntry, GeocodeCacheRepo


def _listing(
    *,
    address: str | None = "1234 W 4th Ave, Vancouver, BC",
    lat: float | None = None,
    lon: float | None = None,
) -> NormalizedListing:
    nid = uuid4()
    now = datetime.now(UTC)
    return NormalizedListing(
        id=nid,
        canonical_id=nid,
        source="craigslist",
        source_url=HttpUrl("https://example.com/listing/1"),
        source_listing_id="1",
        title="Bright 2BR",
        address=address,
        address_normalized=None,
        lat=lat,
        lon=lon,
        bedrooms=2.0,
        bathrooms=None,
        price_cad=2800,
        pets_allowed=None,
        furnished=None,
        available_date=None,
        posted_at=now,
        last_seen_at=now,
        photos=[],
        description_snippet=None,
        school_catchments=SchoolCatchments(),
        raw_metadata={},
    )


class FakeGeocoder:
    def __init__(self, result: GeocodeResult | None = None, *, raises: Exception | None = None):
        self.result = result
        self.raises = raises
        self.calls: list[str] = []

    async def geocode(self, query: str):
        self.calls.append(query)
        if self.raises is not None:
            raise self.raises
        return self.result


@pytest.fixture
def make_service(session):
    def factory(
        geocoder: FakeGeocoder,
        *,
        enabled: bool = True,
        school_catchments_enabled: bool = True,
        transit_enabled: bool = True,
    ) -> EnrichmentService:
        return EnrichmentService(
            cache_repo=GeocodeCacheRepo(session),
            geocoder=geocoder,
            config=EnrichmentConfig(
                enabled=enabled,
                cache_ttl_days=30,
                school_catchments_enabled=school_catchments_enabled,
                transit_enabled=transit_enabled,
            ),
        )

    return factory


@pytest.mark.asyncio
async def test_enrich_disabled_is_noop(make_service):
    geocoder = FakeGeocoder()
    svc = make_service(geocoder, enabled=False)
    listing = _listing()
    out = await svc.enrich(listing)
    assert out is listing  # no copy made, no work done
    assert geocoder.calls == []


@pytest.mark.asyncio
async def test_enrich_no_address_is_noop(make_service):
    geocoder = FakeGeocoder()
    svc = make_service(geocoder)
    listing = _listing(address=None)
    out = await svc.enrich(listing)
    assert out is listing
    assert geocoder.calls == []


@pytest.mark.asyncio
async def test_enrich_unparseable_address_returns_input_unchanged(make_service):
    geocoder = FakeGeocoder()
    svc = make_service(geocoder)
    listing = _listing(address="just some text, no address here")
    out = await svc.enrich(listing)
    assert out is listing
    assert geocoder.calls == []


@pytest.mark.asyncio
async def test_enrich_listing_with_existing_coords_skips_geocoder(make_service):
    geocoder = FakeGeocoder(result=GeocodeResult(lat=99.0, lon=99.0))
    svc = make_service(geocoder)
    listing = _listing(lat=49.26, lon=-123.15)
    out = await svc.enrich(listing)
    assert out.lat == 49.26
    assert out.lon == -123.15
    # Source-supplied coordinates win — the geocoder is not even called.
    assert geocoder.calls == []
    # …but we still record the normalized key so dedup works in PR-C.
    assert out.address_normalized is not None


@pytest.mark.asyncio
async def test_enrich_geocodes_and_caches_when_no_cache(make_service, session):
    geocoder = FakeGeocoder(result=GeocodeResult(lat=49.2661, lon=-123.1525))
    svc = make_service(geocoder)
    listing = _listing()

    out = await svc.enrich(listing)
    assert out.lat == 49.2661
    assert out.lon == -123.1525
    assert out.address_normalized is not None
    assert geocoder.calls == [out.address_normalized]

    # Cache row written.
    cached = await GeocodeCacheRepo(session).get(out.address_normalized)
    assert cached is not None
    assert cached.lat == 49.2661


@pytest.mark.asyncio
async def test_enrich_uses_fresh_cache_hit(make_service, session):
    """Pre-seed the cache; the geocoder must not be called."""
    geocoder = FakeGeocoder(result=GeocodeResult(lat=99.0, lon=99.0))
    svc = make_service(geocoder)
    listing = _listing()

    # Pre-seed the cache with the canonical key the listing will produce.
    from rentwise.enrichment.address import normalize_address

    key = normalize_address(listing.address)
    assert key is not None
    now = datetime.now(UTC)
    await GeocodeCacheRepo(session).upsert(
        GeocodeCacheEntry(
            address_key=key,
            lat=49.0,
            lon=-123.0,
            provider="nominatim",
            fetched_at=now.isoformat(),
            stale_after=(now + timedelta(days=10)).isoformat(),
        )
    )

    out = await svc.enrich(listing)
    assert out.lat == 49.0
    assert out.lon == -123.0
    assert geocoder.calls == []  # cache hit


@pytest.mark.asyncio
async def test_enrich_refreshes_stale_cache(make_service, session):
    geocoder = FakeGeocoder(result=GeocodeResult(lat=49.5, lon=-123.5))
    svc = make_service(geocoder)
    listing = _listing()

    from rentwise.enrichment.address import normalize_address

    key = normalize_address(listing.address)
    assert key is not None
    past = datetime.now(UTC) - timedelta(days=1)
    await GeocodeCacheRepo(session).upsert(
        GeocodeCacheEntry(
            address_key=key,
            lat=49.0,
            lon=-123.0,
            provider="nominatim",
            fetched_at=past.isoformat(),
            stale_after=past.isoformat(),
        )
    )

    out = await svc.enrich(listing)
    assert out.lat == 49.5  # refreshed
    assert geocoder.calls == [key]


@pytest.mark.asyncio
async def test_enrich_swallows_geocode_error(make_service):
    geocoder = FakeGeocoder(raises=GeocodeError("boom"))
    svc = make_service(geocoder)
    listing = _listing()

    out = await svc.enrich(listing)
    assert out.lat is None
    assert out.lon is None
    # Even on failure, the canonical key was still computed and stored.
    assert out.address_normalized is not None


@pytest.mark.asyncio
async def test_enrich_caches_negative_result(make_service, session):
    geocoder = FakeGeocoder(result=None)
    svc = make_service(geocoder)
    # Syntactically valid (pyap parses it) but Nominatim returns nothing.
    listing = _listing(address="99999 Imaginary Ave, Vancouver, BC")

    out = await svc.enrich(listing)
    assert out.lat is None
    assert out.lon is None
    assert out.address_normalized is not None

    cached = await GeocodeCacheRepo(session).get(out.address_normalized)
    assert cached is not None
    assert cached.lat is None
    assert cached.lon is None


@pytest.mark.asyncio
async def test_enrich_populates_school_catchments_when_inside_polygon(make_service):
    """Geocoder returns coords inside the synthetic Lord Byng polygon."""
    geocoder = FakeGeocoder(result=GeocodeResult(lat=49.275, lon=-123.180))
    svc = make_service(geocoder)
    listing = _listing()

    out = await svc.enrich(listing)
    assert out.school_catchments.secondary == "Lord Byng"


@pytest.mark.asyncio
async def test_enrich_populates_nearest_transit_when_within_radius(make_service):
    """Geocoder returns coords near Broadway-City Hall in the synthetic stops."""
    geocoder = FakeGeocoder(result=GeocodeResult(lat=49.263, lon=-123.115))
    svc = make_service(geocoder)
    listing = _listing()

    out = await svc.enrich(listing)
    assert out.nearest_transit is not None
    assert out.nearest_transit.nearest_stop_name == "Broadway-City Hall Station"
    assert out.nearest_transit.line == "Canada Line"
    assert out.nearest_transit.walk_minutes >= 0


@pytest.mark.asyncio
async def test_enrich_skips_school_catchments_when_disabled(make_service):
    geocoder = FakeGeocoder(result=GeocodeResult(lat=49.275, lon=-123.180))
    svc = make_service(geocoder, school_catchments_enabled=False)
    listing = _listing()

    out = await svc.enrich(listing)
    assert out.school_catchments.secondary is None


@pytest.mark.asyncio
async def test_enrich_skips_transit_when_disabled(make_service):
    geocoder = FakeGeocoder(result=GeocodeResult(lat=49.263, lon=-123.115))
    svc = make_service(geocoder, transit_enabled=False)
    listing = _listing()

    out = await svc.enrich(listing)
    assert out.nearest_transit is None
