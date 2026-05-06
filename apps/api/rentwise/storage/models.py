"""SQLAlchemy ORM models. Kept separate from Pydantic — repos own the mapping."""

from __future__ import annotations

from datetime import datetime  # noqa: F401 — kept for future typed columns
from typing import Any  # noqa: F401 — kept for future typed columns

from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    canonical_id: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_listing_id: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    snippet: Mapped[str | None] = mapped_column(String, nullable=True)
    address_raw: Mapped[str | None] = mapped_column(String, nullable=True)
    address_normalized: Mapped[str | None] = mapped_column(String, nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(String, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    bedrooms: Mapped[float | None] = mapped_column(Float, nullable=True)
    bathrooms: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_cad: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pets_allowed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    furnished: Mapped[int | None] = mapped_column(Integer, nullable=True)
    available_date: Mapped[str | None] = mapped_column(String, nullable=True)
    posted_at: Mapped[str] = mapped_column(String, nullable=False)
    last_seen_at: Mapped[str] = mapped_column(String, nullable=False)
    catchment_elementary: Mapped[str | None] = mapped_column(String, nullable=True)
    catchment_middle: Mapped[str | None] = mapped_column(String, nullable=True)
    catchment_secondary: Mapped[str | None] = mapped_column(String, nullable=True)
    photo_urls_json: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_metadata_json: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint("source", "source_listing_id", name="uq_listings_source_id"),
        Index("idx_listings_canonical", "canonical_id"),
        Index("idx_listings_posted_at", "posted_at"),
        Index("idx_listings_price", "price_cad"),
        Index("idx_listings_bedrooms", "bedrooms"),
    )


class CanonicalListing(Base):
    __tablename__ = "canonical_listings"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    primary_listing_id: Mapped[str] = mapped_column(
        String, ForeignKey("listings.id"), nullable=False
    )
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class Search(Base):
    __tablename__ = "searches"
    cache_key: Mapped[str] = mapped_column(String, primary_key=True)
    query_json: Mapped[str] = mapped_column(String, nullable=False)
    last_run_at: Mapped[str] = mapped_column(String, nullable=False)
    listing_ids_json: Mapped[str] = mapped_column(String, nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    is_saved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    user_label: Mapped[str | None] = mapped_column(String, nullable=True)


class SourceHealthRow(Base):
    __tablename__ = "source_health"
    source: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    last_success_at: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error_at: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
