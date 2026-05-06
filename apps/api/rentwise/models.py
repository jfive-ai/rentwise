"""Core data models, shared between the LLM translator, adapters, and the API.

These are the *normalized* shapes — what the rest of the app sees. Each adapter
is responsible for mapping its source-specific format into these.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl


class PetPolicy(StrEnum):
    """User's preference about pets."""

    REQUIRED = "required"  # listing must allow pets
    OK = "ok"  # pets allowed (synonym, kept for clarity)
    NO = "no"  # listing must NOT allow pets
    ANY = "any"  # don't care


class FurnishedPolicy(StrEnum):
    YES = "yes"
    NO = "no"
    ANY = "any"


class NormalizedQuery(BaseModel):
    """The structured search query.

    Both the LLM translator and the filter UI produce instances of this.
    Adapters consume it.
    """

    bedrooms_min: float | None = Field(
        default=None,
        description="Minimum bedrooms. 0.5 means studio acceptable.",
    )
    bedrooms_max: float | None = None
    price_min: int | None = Field(default=None, description="CAD per month")
    price_max: int | None = Field(default=None, description="CAD per month")
    neighborhoods: list[str] = Field(default_factory=list)
    school_catchment: str | None = None
    pets: PetPolicy = PetPolicy.ANY
    furnished: FurnishedPolicy = FurnishedPolicy.ANY
    available_after: date | None = None
    transit_max_walk_minutes: int | None = None
    free_text_keywords: list[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        """True if no constraints are set — matches everything."""
        return self == NormalizedQuery()


class TransitInfo(BaseModel):
    """Distance to the nearest transit stop."""

    nearest_stop_name: str
    walk_minutes: int
    line: str | None = None  # e.g. "Expo Line"


class RawListing(BaseModel):
    """What an adapter returns. Source-specific extras live in `raw_metadata`.

    This is intentionally permissive — adapters may not be able to fill every
    field. The aggregator drops listings that are missing the bare essentials
    (price, address, source_url).
    """

    source: str  # e.g. "craigslist", "livrent"
    source_url: HttpUrl
    source_listing_id: str
    title: str
    address: str | None = None
    lat: float | None = None
    lon: float | None = None
    bedrooms: float | None = None
    bathrooms: float | None = None
    price_cad: int | None = None
    pets_allowed: bool | None = None
    furnished: bool | None = None
    available_date: date | None = None
    posted_at: datetime
    photos: list[HttpUrl] = Field(default_factory=list)
    description_snippet: str | None = Field(
        default=None,
        max_length=200,
        description="Max 200 chars for fair-use snippet display.",
    )
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class SchoolCatchments(BaseModel):
    """Per-level Vancouver school catchments. All optional —
    not every area has a middle school (most VSB is K-7 / 8-12).
    """

    elementary: str | None = None
    middle: str | None = None
    secondary: str | None = None


class NormalizedListing(BaseModel):
    """A listing after normalization, dedup, and enrichment.

    What the frontend actually displays.
    """

    id: UUID = Field(default_factory=uuid4)
    canonical_id: UUID  # listings sharing this ID are duplicates of each other

    source: str
    source_url: HttpUrl
    source_listing_id: str

    title: str
    address: str | None
    address_normalized: str | None  # for dedup matching
    lat: float | None
    lon: float | None

    bedrooms: float | None
    bathrooms: float | None
    price_cad: int | None
    pets_allowed: bool | None
    furnished: bool | None
    available_date: date | None

    posted_at: datetime
    last_seen_at: datetime
    photos: list[HttpUrl]
    description_snippet: str | None

    # Enrichment
    school_catchments: SchoolCatchments = Field(default_factory=SchoolCatchments)
    nearest_transit: TransitInfo | None = None
    walkscore: int | None = None

    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class AdapterHealth(BaseModel):
    """Status of one source adapter."""

    name: str
    status: str  # "ok" | "degraded" | "blocked"
    last_successful_fetch: datetime | None = None
    last_error: str | None = None


class SortOrder(StrEnum):
    NEWEST = "newest"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    BEDROOMS = "bedrooms"


class SearchRequest(BaseModel):
    query: NormalizedQuery
    force_refresh: bool = False
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    sort: SortOrder = SortOrder.NEWEST


class SearchResponse(BaseModel):
    listings: list[NormalizedListing]
    total: int
    cache_status: Literal["fresh", "stale", "miss"]
    unsupported_filters: list[str]
    source_health: dict[str, AdapterHealth]
