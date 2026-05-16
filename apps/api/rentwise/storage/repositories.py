"""Repositories: ORM ↔ Pydantic mapping. The only place SQLAlchemy types appear."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.models import AdapterHealth, NormalizedListing, SchoolCatchments, TransitInfo
from rentwise.storage.models import (
    AlertLogRow,
    GeocodeCacheRow,
    Listing,
    PhotoHashCacheRow,
    Search,
    SourceHealthRow,
    WebPushSubscriptionRow,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _to_pydantic(row: Listing) -> NormalizedListing:
    return NormalizedListing(
        id=UUID(row.id),
        canonical_id=UUID(row.canonical_id) if row.canonical_id else UUID(row.id),
        source=row.source,
        source_url=HttpUrl(row.source_url),
        source_listing_id=row.source_listing_id,
        title=row.title,
        address=row.address_raw,
        address_normalized=row.address_normalized,
        # Codex P1 on PR #133: surface the persisted neighborhood column —
        # was hardcoded to None on insert and ignored on read, so cached
        # listings lost their area assignment between requests.
        neighborhood=row.neighborhood,
        lat=row.lat,
        lon=row.lon,
        bedrooms=row.bedrooms,
        bathrooms=row.bathrooms,
        price_cad=row.price_cad,
        pets_allowed=None if row.pets_allowed is None else bool(row.pets_allowed),
        furnished=None if row.furnished is None else bool(row.furnished),
        available_date=(
            datetime.fromisoformat(row.available_date).date() if row.available_date else None
        ),
        posted_at=datetime.fromisoformat(row.posted_at),
        last_seen_at=datetime.fromisoformat(row.last_seen_at),
        photos=[HttpUrl(u) for u in json.loads(row.photo_urls_json or "[]")],
        description_snippet=row.snippet,
        school_catchments=SchoolCatchments(
            elementary=row.catchment_elementary,
            middle=row.catchment_middle,
            secondary=row.catchment_secondary,
        ),
        nearest_transit=(
            TransitInfo(
                nearest_stop_name=row.nearest_transit_stop,
                walk_minutes=row.nearest_transit_walk_minutes,
                line=row.nearest_transit_line,
            )
            if row.nearest_transit_stop is not None and row.nearest_transit_walk_minutes is not None
            else None
        ),
        phash=row.phash,
        raw_metadata=json.loads(row.raw_metadata_json or "{}"),
    )


class ListingRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_source(self, source: str, source_listing_id: str) -> NormalizedListing | None:
        stmt = select(Listing).where(
            Listing.source == source, Listing.source_listing_id == source_listing_id
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return _to_pydantic(row) if row else None

    async def list_by_ids(self, ids: list[str]) -> list[NormalizedListing]:
        if not ids:
            return []
        stmt = select(Listing).where(Listing.id.in_(ids))
        rows = (await self.session.execute(stmt)).scalars().all()
        by_id = {r.id: r for r in rows}
        return [_to_pydantic(by_id[i]) for i in ids if i in by_id]

    async def upsert(self, listing: NormalizedListing) -> NormalizedListing:
        existing_stmt = select(Listing).where(
            Listing.source == listing.source,
            Listing.source_listing_id == listing.source_listing_id,
        )
        existing = (await self.session.execute(existing_stmt)).scalar_one_or_none()

        now = _now_iso()
        if existing is None:
            new_id = str(listing.id) if isinstance(listing.id, UUID) else str(uuid4())
            row = Listing(
                id=new_id,
                canonical_id=str(listing.canonical_id) if listing.canonical_id else None,
                source=listing.source,
                source_listing_id=listing.source_listing_id,
                source_url=str(listing.source_url),
                title=listing.title,
                snippet=listing.description_snippet,
                address_raw=listing.address,
                address_normalized=listing.address_normalized,
                # Codex P1 on PR #133 — was hardcoded None, dropping the
                # enriched neighborhood on every insert. Now we persist
                # the value the caller assigned (geocode lookup or, in
                # demo mode, the raw_metadata hint).
                neighborhood=listing.neighborhood,
                lat=listing.lat,
                lon=listing.lon,
                bedrooms=listing.bedrooms,
                bathrooms=listing.bathrooms,
                price_cad=listing.price_cad,
                pets_allowed=None if listing.pets_allowed is None else int(listing.pets_allowed),
                furnished=None if listing.furnished is None else int(listing.furnished),
                available_date=listing.available_date.isoformat()
                if listing.available_date
                else None,
                posted_at=listing.posted_at.isoformat(),
                last_seen_at=listing.last_seen_at.isoformat(),
                catchment_elementary=listing.school_catchments.elementary,
                catchment_middle=listing.school_catchments.middle,
                catchment_secondary=listing.school_catchments.secondary,
                nearest_transit_stop=(
                    listing.nearest_transit.nearest_stop_name
                    if listing.nearest_transit is not None
                    else None
                ),
                nearest_transit_walk_minutes=(
                    listing.nearest_transit.walk_minutes
                    if listing.nearest_transit is not None
                    else None
                ),
                nearest_transit_line=(
                    listing.nearest_transit.line if listing.nearest_transit is not None else None
                ),
                phash=listing.phash,
                photo_urls_json=json.dumps([str(u) for u in listing.photos]),
                raw_metadata_json=json.dumps(listing.raw_metadata or {}),
                created_at=now,
                updated_at=now,
            )
            self.session.add(row)
        else:
            existing.title = listing.title
            existing.snippet = listing.description_snippet
            existing.address_normalized = listing.address_normalized
            # Codex P1 on PR #133 — keep neighborhood in sync on updates.
            # Don't overwrite a previously-set value with None, since
            # subsequent re-enrichment with a stuck geocoder would erase
            # known data.
            if listing.neighborhood is not None:
                existing.neighborhood = listing.neighborhood
            existing.lat = listing.lat
            existing.lon = listing.lon
            existing.bedrooms = listing.bedrooms
            existing.bathrooms = listing.bathrooms
            existing.price_cad = listing.price_cad
            existing.last_seen_at = listing.last_seen_at.isoformat()
            existing.catchment_elementary = listing.school_catchments.elementary
            existing.catchment_middle = listing.school_catchments.middle
            existing.catchment_secondary = listing.school_catchments.secondary
            if listing.nearest_transit is not None:
                existing.nearest_transit_stop = listing.nearest_transit.nearest_stop_name
                existing.nearest_transit_walk_minutes = listing.nearest_transit.walk_minutes
                existing.nearest_transit_line = listing.nearest_transit.line
            else:
                existing.nearest_transit_stop = None
                existing.nearest_transit_walk_minutes = None
                existing.nearest_transit_line = None
            # Don't overwrite an existing phash with None — re-enrichment
            # may not re-fetch the photo (cache hit / disabled / no URL).
            if listing.phash is not None:
                existing.phash = listing.phash
            # canonical_id is owned by the dedup pass; if the new listing
            # carries a different canonical_id (e.g. it merged into an
            # existing cluster), propagate it.
            if listing.canonical_id is not None:
                existing.canonical_id = str(listing.canonical_id)
            existing.updated_at = now
            row = existing

        await self.session.flush()
        return _to_pydantic(row)


# ---------------------------------------------------------------------------
# SearchRepo
# ---------------------------------------------------------------------------


@dataclass
class CachedSearch:
    cache_key: str
    query_json: str
    listing_ids: list[str]
    total_count: int
    last_run_at: str | None = None  # set on read
    is_saved: bool = False


@dataclass
class SavedSearch:
    """One row of the saved-search list returned to the user."""

    cache_key: str
    query_json: str
    user_label: str | None
    alert_enabled: bool
    alert_email: str | None
    alert_cadence_minutes: int
    last_run_at: str
    total_count: int


class SearchRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, cache_key: str) -> CachedSearch | None:
        row = await self.session.get(Search, cache_key)
        if row is None:
            return None
        return CachedSearch(
            cache_key=row.cache_key,
            query_json=row.query_json,
            listing_ids=json.loads(row.listing_ids_json),
            total_count=row.total_count,
            last_run_at=row.last_run_at,
            is_saved=bool(row.is_saved),
        )

    async def upsert(self, cs: CachedSearch) -> None:
        existing = await self.session.get(Search, cs.cache_key)
        now = _now_iso()
        if existing is None:
            self.session.add(
                Search(
                    cache_key=cs.cache_key,
                    query_json=cs.query_json,
                    last_run_at=now,
                    listing_ids_json=json.dumps(cs.listing_ids),
                    total_count=cs.total_count,
                    is_saved=int(cs.is_saved),
                    user_label=None,
                )
            )
        else:
            existing.query_json = cs.query_json
            existing.last_run_at = now
            existing.listing_ids_json = json.dumps(cs.listing_ids)
            existing.total_count = cs.total_count
            existing.is_saved = int(cs.is_saved)
        await self.session.flush()

    # ---- Phase 5 PR-A: saved-search CRUD ----

    async def save(
        self,
        cache_key: str,
        *,
        label: str | None,
        alert_enabled: bool = False,
        alert_email: str | None = None,
        cadence_minutes: int | None = None,
    ) -> SavedSearch | None:
        """Mark an existing search row as saved + attach alert metadata.

        Returns ``None`` if no search row exists for ``cache_key`` yet —
        saves piggyback on the existing search cache, so the user must
        run a search at least once before saving it.

        ``cadence_minutes`` is optional: when omitted the existing
        column value is preserved (so re-saving a previously-deleted
        saved search keeps the user's cadence choice).
        """
        row = await self.session.get(Search, cache_key)
        if row is None:
            return None
        row.is_saved = 1
        row.user_label = label
        row.alert_enabled = 1 if alert_enabled else 0
        row.alert_email = alert_email
        if cadence_minutes is not None:
            row.alert_cadence_minutes = cadence_minutes
        await self.session.flush()
        return _to_saved(row)

    async def list_saved(self) -> list[SavedSearch]:
        stmt = select(Search).where(Search.is_saved == 1).order_by(Search.last_run_at.desc())
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_to_saved(r) for r in rows]

    async def delete_saved(self, cache_key: str) -> bool:
        """Clear the saved-search flags. Returns True if a row was updated.

        We don't physically delete the search row — the cache row may
        still be useful for non-saved use. Just unset the saved flags.
        """
        row = await self.session.get(Search, cache_key)
        if row is None or not row.is_saved:
            return False
        row.is_saved = 0
        row.user_label = None
        row.alert_enabled = 0
        row.alert_email = None
        # Leave cadence at whatever the user picked; if they save again
        # later it preserves their preferred frequency.
        await self.session.flush()
        return True


def _to_saved(row: Search) -> SavedSearch:
    return SavedSearch(
        cache_key=row.cache_key,
        query_json=row.query_json,
        user_label=row.user_label,
        alert_enabled=bool(row.alert_enabled),
        alert_email=row.alert_email,
        alert_cadence_minutes=row.alert_cadence_minutes,
        last_run_at=row.last_run_at,
        total_count=row.total_count,
    )


# ---------------------------------------------------------------------------
# SourceHealthRepo
# ---------------------------------------------------------------------------


class SourceHealthRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, source: str) -> AdapterHealth | None:
        row = await self.session.get(SourceHealthRow, source)
        if row is None:
            return None
        return AdapterHealth(
            name=row.source,
            status=row.status,
            last_successful_fetch=(
                datetime.fromisoformat(row.last_success_at) if row.last_success_at else None
            ),
            last_error=row.last_error_message,
        )

    async def set(self, source: str, status: str, error: str | None) -> None:
        row = await self.session.get(SourceHealthRow, source)
        now = _now_iso()
        if row is None:
            row = SourceHealthRow(
                source=source,
                status=status,
                last_success_at=now if status == "ok" else None,
                last_error_at=now if error else None,
                last_error_message=error,
                consecutive_failures=0 if status == "ok" else 1,
                updated_at=now,
            )
            self.session.add(row)
        else:
            row.status = status
            row.updated_at = now
            if status == "ok":
                row.last_success_at = now
                row.last_error_message = None
                row.consecutive_failures = 0
            else:
                row.last_error_at = now
                row.last_error_message = error
                row.consecutive_failures += 1
        await self.session.flush()


# ---------------------------------------------------------------------------
# GeocodeCacheRepo (Phase 4 PR-A)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GeocodeCacheEntry:
    address_key: str
    lat: float | None
    lon: float | None
    provider: str
    fetched_at: str  # ISO8601
    stale_after: str  # ISO8601


class GeocodeCacheRepo:
    """Persistent cache for geocoder lookups.

    A row exists for every address we've asked the geocoder about, including
    *negative* results (lat / lon both null). That keeps us from hammering
    Nominatim repeatedly for addresses it can't resolve. ``stale_after`` lets
    callers decide whether to trust a cached row or refresh.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, address_key: str) -> GeocodeCacheEntry | None:
        row = await self.session.get(GeocodeCacheRow, address_key)
        if row is None:
            return None
        return GeocodeCacheEntry(
            address_key=row.address_key,
            lat=row.lat,
            lon=row.lon,
            provider=row.provider,
            fetched_at=row.fetched_at,
            stale_after=row.stale_after,
        )

    async def upsert(self, entry: GeocodeCacheEntry) -> None:
        existing = await self.session.get(GeocodeCacheRow, entry.address_key)
        if existing is None:
            self.session.add(
                GeocodeCacheRow(
                    address_key=entry.address_key,
                    lat=entry.lat,
                    lon=entry.lon,
                    provider=entry.provider,
                    fetched_at=entry.fetched_at,
                    stale_after=entry.stale_after,
                )
            )
        else:
            existing.lat = entry.lat
            existing.lon = entry.lon
            existing.provider = entry.provider
            existing.fetched_at = entry.fetched_at
            existing.stale_after = entry.stale_after
        await self.session.flush()

    @staticmethod
    def is_stale(entry: GeocodeCacheEntry, *, now: datetime | None = None) -> bool:
        """True if ``entry.stale_after`` is in the past relative to ``now``."""
        moment = now or datetime.now(UTC)
        try:
            cutoff = datetime.fromisoformat(entry.stale_after)
        except ValueError:
            # Unparseable cutoff → treat as stale so we re-fetch.
            return True
        return moment >= cutoff


# ---------------------------------------------------------------------------
# PhotoHashCacheRepo (Phase 4 PR-C)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PhotoHashCacheEntry:
    url: str
    phash: str | None  # hex-encoded 64-bit perceptual hash; None = "fetch failed / not an image"
    fetched_at: str  # ISO8601
    stale_after: str  # ISO8601


class PhotoHashCacheRepo:
    """Persistent cache for image perceptual hashes keyed by URL.

    Mirrors :class:`GeocodeCacheRepo`; the difference is the cache key
    (a photo URL, not a normalized address) and the stored value (a
    pHash hex string, not lat/lon).
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, url: str) -> PhotoHashCacheEntry | None:
        row = await self.session.get(PhotoHashCacheRow, url)
        if row is None:
            return None
        return PhotoHashCacheEntry(
            url=row.url,
            phash=row.phash,
            fetched_at=row.fetched_at,
            stale_after=row.stale_after,
        )

    async def upsert(self, entry: PhotoHashCacheEntry) -> None:
        existing = await self.session.get(PhotoHashCacheRow, entry.url)
        if existing is None:
            self.session.add(
                PhotoHashCacheRow(
                    url=entry.url,
                    phash=entry.phash,
                    fetched_at=entry.fetched_at,
                    stale_after=entry.stale_after,
                )
            )
        else:
            existing.phash = entry.phash
            existing.fetched_at = entry.fetched_at
            existing.stale_after = entry.stale_after
        await self.session.flush()

    @staticmethod
    def is_stale(entry: PhotoHashCacheEntry, *, now: datetime | None = None) -> bool:
        moment = now or datetime.now(UTC)
        try:
            cutoff = datetime.fromisoformat(entry.stale_after)
        except ValueError:
            return True
        return moment >= cutoff


# ---------------------------------------------------------------------------
# AlertLogRepo (Phase 5 PR-B)
# ---------------------------------------------------------------------------


class AlertLogRepo:
    """Dedup ledger for saved-search alert dispatches.

    The runner consults ``get_alerted_ids`` to subtract listings already
    notified-on, and calls ``record_alerted`` after a *successful*
    notification dispatch. A failed dispatch must NOT call
    ``record_alerted`` — otherwise we'd silently drop the user's first
    alert for that listing.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_alerted_ids(self, cache_key: str, *, channel: str = "email") -> set[str]:
        """Listings already notified-on for ``cache_key`` via ``channel``.

        Per-channel dedup means email and web push each maintain their
        own ledger column-side, so adding a new channel later still
        notifies for backlog listings the user previously got via the
        other channel.
        """
        stmt = select(AlertLogRow.listing_id).where(
            AlertLogRow.cache_key == cache_key,
            AlertLogRow.channel == channel,
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return set(rows)

    async def record_alerted(
        self,
        cache_key: str,
        listing_ids: list[str],
        *,
        channel: str = "email",
    ) -> None:
        if not listing_ids:
            return
        now = _now_iso()
        # Use a per-row insert with skip-on-conflict semantics. SQLite has
        # `INSERT OR IGNORE`; SQLAlchemy's higher-level API doesn't expose
        # that portably, so we filter against the existing set first.
        existing = await self.get_alerted_ids(cache_key, channel=channel)
        for lid in listing_ids:
            if lid in existing:
                continue
            self.session.add(
                AlertLogRow(
                    cache_key=cache_key,
                    listing_id=lid,
                    alerted_at=now,
                    channel=channel,
                )
            )
        await self.session.flush()


# ---------------------------------------------------------------------------
# WebPushSubscriptionRepo (Phase 5 PR-C)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WebPushSubscription:
    id: int
    endpoint: str
    p256dh: str
    auth: str
    alert_email: str | None
    label: str | None
    created_at: str
    last_seen_at: str


class WebPushSubscriptionRepo:
    """Persistence layer for browser web-push subscriptions.

    Subscriptions are tagged with ``alert_email`` so the notifier can
    route a saved-search alert to all subscriptions that share its
    email. The natural key is ``endpoint`` (per RFC 8030) — the same
    browser/origin re-subscribing produces the same endpoint and we
    update in place rather than creating duplicates.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_endpoint(self, endpoint: str) -> WebPushSubscription | None:
        stmt = select(WebPushSubscriptionRow).where(WebPushSubscriptionRow.endpoint == endpoint)
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return _to_subscription(row) if row else None

    async def upsert(
        self,
        *,
        endpoint: str,
        p256dh: str,
        auth: str,
        alert_email: str | None,
        label: str | None,
    ) -> WebPushSubscription:
        existing_stmt = select(WebPushSubscriptionRow).where(
            WebPushSubscriptionRow.endpoint == endpoint
        )
        existing = (await self.session.execute(existing_stmt)).scalar_one_or_none()
        now = _now_iso()
        if existing is None:
            row = WebPushSubscriptionRow(
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth,
                alert_email=alert_email,
                label=label,
                created_at=now,
                last_seen_at=now,
            )
            self.session.add(row)
        else:
            existing.p256dh = p256dh
            existing.auth = auth
            existing.alert_email = alert_email
            existing.label = label
            existing.last_seen_at = now
            row = existing
        await self.session.flush()
        return _to_subscription(row)

    async def list_for_email(self, alert_email: str) -> list[WebPushSubscription]:
        stmt = select(WebPushSubscriptionRow).where(
            WebPushSubscriptionRow.alert_email == alert_email
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_to_subscription(r) for r in rows]

    async def delete(self, sub_id: int) -> bool:
        row = await self.session.get(WebPushSubscriptionRow, sub_id)
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True

    async def delete_by_endpoint(self, endpoint: str) -> bool:
        """Used by the notifier when the push service returns 410 Gone."""
        stmt = select(WebPushSubscriptionRow).where(WebPushSubscriptionRow.endpoint == endpoint)
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True


def _to_subscription(row: WebPushSubscriptionRow) -> WebPushSubscription:
    return WebPushSubscription(
        id=row.id,
        endpoint=row.endpoint,
        p256dh=row.p256dh,
        auth=row.auth,
        alert_email=row.alert_email,
        label=row.label,
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
    )
