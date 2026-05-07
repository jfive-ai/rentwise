"""Repositories: ORM ↔ Pydantic mapping. The only place SQLAlchemy types appear."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.models import AdapterHealth, NormalizedListing, SchoolCatchments
from rentwise.storage.models import Listing, Search, SourceHealthRow


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
                neighborhood=None,
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
                first_seen_at=listing.posted_at.isoformat(),
                capture_method="server",
                catchment_elementary=listing.school_catchments.elementary,
                catchment_middle=listing.school_catchments.middle,
                catchment_secondary=listing.school_catchments.secondary,
                photo_urls_json=json.dumps([str(u) for u in listing.photos]),
                raw_metadata_json=json.dumps(listing.raw_metadata or {}),
                created_at=now,
                updated_at=now,
            )
            self.session.add(row)
        else:
            existing.title = listing.title
            existing.snippet = listing.description_snippet
            existing.lat = listing.lat
            existing.lon = listing.lon
            existing.bedrooms = listing.bedrooms
            existing.bathrooms = listing.bathrooms
            existing.price_cad = listing.price_cad
            existing.last_seen_at = listing.last_seen_at.isoformat()
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
