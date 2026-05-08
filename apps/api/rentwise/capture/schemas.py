"""Pydantic models for the /capture endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

# Mirrors the source identifiers used by the extension content scripts.
# Adding a new source requires bumping this list AND the extension manifest.
SourceId = Literal[
    "rentals_ca",
    "padmapper",
    "zumper",
    "rew_ca",
    "liv_rent",
    "facebook_marketplace",
]

PageType = Literal["search_results", "listing_detail"]


class CaptureListing(BaseModel):
    """One listing extracted from a rendered page in the user's browser.

    Mirrors `RawListing` plus `capture_method` + `page_type`. Snippet length
    is hard-capped at 200 chars per `docs/operational-rules.md`.
    """

    source_listing_id: str = Field(min_length=1, max_length=200)
    url: HttpUrl
    title: str | None = Field(default=None, max_length=500)
    price: int | None = Field(default=None, ge=0, le=1_000_000)
    bedrooms: float | None = Field(default=None, ge=0, le=20)
    bathrooms: float | None = Field(default=None, ge=0, le=20)
    sqft: int | None = Field(default=None, ge=0, le=100_000)
    neighborhood: str | None = Field(default=None, max_length=200)
    posted_at: datetime | None = None
    thumbnail_url: HttpUrl | None = None
    photo_urls: list[HttpUrl] = Field(default_factory=list)
    description_snippet: str | None = Field(default=None, max_length=200)

    capture_method: Literal["extension"] = "extension"
    page_type: PageType


class CapturePayload(BaseModel):
    source: SourceId
    captured_at: datetime
    page_type: PageType
    page_url: HttpUrl
    schema_version: str = Field(min_length=1, max_length=64)
    listings: list[CaptureListing] = Field(default_factory=list, max_length=500)


class CaptureItemError(BaseModel):
    index: int
    message: str


class CaptureResponse(BaseModel):
    accepted: int = 0
    skipped_duplicates: int = 0
    errors: list[CaptureItemError] = Field(default_factory=list)


class CaptureHealthPayload(BaseModel):
    source: SourceId
    schema_version: str = Field(min_length=1, max_length=64)
    status: Literal["degraded"]
    reason: str = Field(min_length=1, max_length=500)


class CapturePairResponse(BaseModel):
    token: str
    server_url: str
