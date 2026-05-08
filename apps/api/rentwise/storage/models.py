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
    first_seen_at: Mapped[str] = mapped_column(String, nullable=False)
    capture_method: Mapped[str] = mapped_column(String, nullable=False, default="server")
    catchment_elementary: Mapped[str | None] = mapped_column(String, nullable=True)
    catchment_middle: Mapped[str | None] = mapped_column(String, nullable=True)
    catchment_secondary: Mapped[str | None] = mapped_column(String, nullable=True)
    nearest_transit_stop: Mapped[str | None] = mapped_column(String, nullable=True)
    nearest_transit_walk_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nearest_transit_line: Mapped[str | None] = mapped_column(String, nullable=True)
    phash: Mapped[str | None] = mapped_column(String, nullable=True)
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
    # Phase 5 PR-A: alert wiring. PR-B reads these to schedule jobs +
    # deliver notifications.
    alert_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    alert_email: Mapped[str | None] = mapped_column(String, nullable=True)
    alert_cadence_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)


class SourceHealthRow(Base):
    __tablename__ = "source_health"
    source: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    last_success_at: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error_at: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class CapturePairingRow(Base):
    """Singleton row holding the shared secret paired with the browser extension.

    The id column is constrained to 1 by the application layer + DB CHECK.
    """

    __tablename__ = "capture_pairing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    rotated_at: Mapped[str | None] = mapped_column(String, nullable=True)


class AlertLogRow(Base):
    """Dedup ledger for saved-search alert dispatches.

    Composite PK on (cache_key, listing_id, channel) — re-running the
    same saved search on the same listing must produce zero new alerts
    for any channel that already notified, but enabling a new channel
    later (e.g. adding web push to a saved search that previously only
    emailed) does fire that channel for the existing backlog.
    """

    __tablename__ = "alert_log"

    cache_key: Mapped[str] = mapped_column(String, primary_key=True)
    listing_id: Mapped[str] = mapped_column(String, primary_key=True)
    channel: Mapped[str] = mapped_column(String, primary_key=True, default="email")
    alerted_at: Mapped[str] = mapped_column(String, nullable=False)


class WebPushSubscriptionRow(Base):
    """One row per browser/origin web-push subscription (Phase 5 PR-C).

    See ``apps/api/alembic/versions/0009_web_push.py`` for the table
    definition. ``endpoint`` is the natural unique key the browser's
    push service hands us at subscribe time. ``alert_email`` routes
    the subscription to whichever saved searches share that address.
    """

    __tablename__ = "web_push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    endpoint: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(String, nullable=False)
    auth: Mapped[str] = mapped_column(String, nullable=False)
    alert_email: Mapped[str | None] = mapped_column(String, nullable=True)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    last_seen_at: Mapped[str] = mapped_column(String, nullable=False)


class GeocodeCacheRow(Base):
    """One row per normalized address; lat/lon nullable for negative results.

    See ``apps/api/alembic/versions/0004_geocode_cache.py`` for the table
    definition. ``stale_after`` is an ISO8601 timestamp at which a cached
    miss/hit becomes stale and should be re-fetched.
    """

    __tablename__ = "geocode_cache"

    address_key: Mapped[str] = mapped_column(String, primary_key=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    fetched_at: Mapped[str] = mapped_column(String, nullable=False)
    stale_after: Mapped[str] = mapped_column(String, nullable=False)


class PhotoHashCacheRow(Base):
    """Cached perceptual hashes keyed by photo URL.

    See migration 0006 + ``apps/api/rentwise/enrichment/photo_hash.py``.
    A row exists for every URL we've fetched (positive or negative
    result), so we don't re-download the same image repeatedly.
    """

    __tablename__ = "photo_hash_cache"

    url: Mapped[str] = mapped_column(String, primary_key=True)
    phash: Mapped[str | None] = mapped_column(String, nullable=True)
    fetched_at: Mapped[str] = mapped_column(String, nullable=False)
    stale_after: Mapped[str] = mapped_column(String, nullable=False)


class LLMSettingsRow(Base):
    """Single-row table holding the user's LLM provider configuration.

    The id column is constrained to 1 by the application layer (the repo).
    API keys are Fernet-encrypted at rest.
    """

    __tablename__ = "llm_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    primary_model: Mapped[str] = mapped_column(String, nullable=False)
    primary_api_key_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    fallback_model: Mapped[str | None] = mapped_column(String, nullable=True)
    fallback_api_key_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    custom_base_url: Mapped[str | None] = mapped_column(String, nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
