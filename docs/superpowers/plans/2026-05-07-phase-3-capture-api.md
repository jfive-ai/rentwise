# Phase 3 PR-A — Backend `/capture` Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the local capture API the browser extension will POST to in PR-B/PR-C. Test-only — no extension or web-app changes here.

**Architecture:** New `rentwise.capture` package with four small modules (`schemas`, `auth`, `pairing`, `router`). Adds an Alembic migration that extends `listings` with `capture_method` + `first_seen_at` and creates the singleton `capture_pairing` table. Extends `ListingRepo` with `upsert_by_source_url` (null-skip merge, detail-wins for descriptive fields). Auth is a shared-secret header verified with `hmac.compare_digest`; pair endpoints are gated by `Origin`.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic, pytest+pytest-asyncio, ruff.

**Source spec:** `docs/superpowers/specs/2026-05-07-phase-3-launcher-extension-design.md` § 6, § 7, § 14.

---

## File Structure

**Create:**
- `apps/api/alembic/versions/0003_capture.py` — migration
- `apps/api/rentwise/capture/__init__.py` — package marker
- `apps/api/rentwise/capture/schemas.py` — `CaptureListing`, `CapturePayload`, `CaptureResponse`, `CaptureHealthPayload`, `CapturePairResponse`
- `apps/api/rentwise/capture/auth.py` — `verify_capture_token` dep + `verify_local_origin` dep
- `apps/api/rentwise/capture/pairing.py` — `CapturePairingRepo`
- `apps/api/rentwise/capture/router.py` — `build_router()` exposing `/capture`, `/capture/health`, `/capture/pair`, `/capture/pair/rotate`
- `apps/api/tests/capture/__init__.py`
- `apps/api/tests/capture/test_schemas.py`
- `apps/api/tests/capture/test_auth.py`
- `apps/api/tests/capture/test_pairing_repo.py`
- `apps/api/tests/capture/test_pairing_router.py`
- `apps/api/tests/capture/test_capture_router.py`
- `apps/api/tests/capture/test_health_router.py`
- `apps/api/tests/storage/test_listing_upsert_by_source_url.py`

**Modify:**
- `apps/api/rentwise/storage/models.py` — add `capture_method`, `first_seen_at` columns to `Listing`; add `CapturePairingRow`
- `apps/api/rentwise/storage/repositories.py` — add `ListingRepo.upsert_by_source_url(...)`
- `apps/api/rentwise/main.py` — register the capture router

---

## Task 1: Migration 0003 — capture_method + first_seen_at + capture_pairing

**Files:**
- Create: `apps/api/alembic/versions/0003_capture.py`
- Modify: `apps/api/rentwise/storage/models.py` (add columns + new ORM table)
- Test: `apps/api/tests/capture/test_pairing_repo.py` (smoke — confirms the migration created the table by inserting/selecting from it via the repo)

- [ ] **Step 1.1: Add the new ORM columns + `CapturePairingRow` to `storage/models.py`**

Edit `apps/api/rentwise/storage/models.py`. Add `capture_method` and `first_seen_at` to `Listing`, and add a new `CapturePairingRow` class:

```python
# In Listing class, after `last_seen_at`:
    capture_method: Mapped[str] = mapped_column(String, nullable=False, default="server")
    first_seen_at: Mapped[str] = mapped_column(String, nullable=False)

# After SourceHealthRow, before LLMSettingsRow:
class CapturePairingRow(Base):
    """Singleton row holding the shared secret paired with the browser extension.

    The id column is constrained to 1 by the application layer + DB CHECK.
    """

    __tablename__ = "capture_pairing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    rotated_at: Mapped[str | None] = mapped_column(String, nullable=True)
```

- [ ] **Step 1.2: Write the migration**

Create `apps/api/alembic/versions/0003_capture.py`:

```python
"""Phase 3 capture support: capture_method + first_seen_at + capture_pairing.

Revision ID: 0003_capture
Revises: 0002_llm_settings
Create Date: 2026-05-07
"""

from __future__ import annotations

from alembic import op

revision = "0003_capture"
down_revision = "0002_llm_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite ALTER TABLE supports adding columns. CHECK constraints on added
    # columns are not enforced retroactively but are enforced for new rows.
    op.execute(
        "ALTER TABLE listings ADD COLUMN capture_method TEXT "
        "NOT NULL DEFAULT 'server' "
        "CHECK (capture_method IN ('server', 'extension'))"
    )
    op.execute(
        "ALTER TABLE listings ADD COLUMN first_seen_at TEXT "
        "NOT NULL DEFAULT CURRENT_TIMESTAMP"
    )
    op.execute("CREATE INDEX idx_listings_capture_method ON listings(capture_method)")

    op.execute(
        """
        CREATE TABLE capture_pairing (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            token       TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            rotated_at  TEXT
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS capture_pairing")
    op.execute("DROP INDEX IF EXISTS idx_listings_capture_method")
    # SQLite cannot drop columns pre-3.35 without a table rebuild; for our
    # MVP we accept that downgrade leaves the columns in place.
```

- [ ] **Step 1.3: Run the existing migration test to verify head still applies**

Run from `apps/api/`:
```
pytest tests/storage/test_migration.py -v
```
Expected: PASS — confirms `0003_capture` chains cleanly off `0002_llm_settings`.

- [ ] **Step 1.4: Commit**

```
git add apps/api/alembic/versions/0003_capture.py apps/api/rentwise/storage/models.py
git commit -m "feat(api): migration 0003 — capture_method + capture_pairing (#21)"
```

---

## Task 2: Pydantic capture schemas

**Files:**
- Create: `apps/api/rentwise/capture/__init__.py` (empty)
- Create: `apps/api/rentwise/capture/schemas.py`
- Test: `apps/api/tests/capture/__init__.py` (empty), `apps/api/tests/capture/test_schemas.py`

- [ ] **Step 2.1: Write the failing schema tests**

Create `apps/api/tests/capture/test_schemas.py`:

```python
"""Tests for capture Pydantic schemas — snippet length cap, page_type literal, source enum."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from rentwise.capture.schemas import (
    CaptureHealthPayload,
    CaptureListing,
    CapturePayload,
)


def _good_listing(**overrides) -> dict:
    base = {
        "source_listing_id": "abc123",
        "url": "https://rentals.ca/listing/abc123",
        "page_type": "listing_detail",
    }
    base.update(overrides)
    return base


def test_capture_listing_minimal_ok():
    obj = CaptureListing(**_good_listing())
    assert obj.capture_method == "extension"
    assert obj.page_type == "listing_detail"


def test_capture_listing_rejects_oversize_snippet():
    too_long = "x" * 201
    with pytest.raises(ValidationError):
        CaptureListing(**_good_listing(description_snippet=too_long))


def test_capture_listing_accepts_200_char_snippet():
    just_right = "x" * 200
    obj = CaptureListing(**_good_listing(description_snippet=just_right))
    assert obj.description_snippet == just_right


def test_capture_listing_rejects_unknown_page_type():
    with pytest.raises(ValidationError):
        CaptureListing(**_good_listing(page_type="random_other"))


def test_capture_payload_rejects_unknown_source():
    with pytest.raises(ValidationError):
        CapturePayload(
            source="not_a_real_site",
            captured_at=datetime.now(UTC),
            page_type="search_results",
            page_url="https://example.com/x",
            schema_version="2026-05-07",
            listings=[],
        )


def test_capture_payload_allows_empty_listings():
    obj = CapturePayload(
        source="rentals_ca",
        captured_at=datetime.now(UTC),
        page_type="search_results",
        page_url="https://rentals.ca/vancouver",
        schema_version="2026-05-07",
        listings=[],
    )
    assert obj.listings == []


def test_capture_health_payload_status_literal():
    obj = CaptureHealthPayload(
        source="rentals_ca",
        schema_version="2026-05-07",
        status="degraded",
        reason="searchResultsCard selector missing",
    )
    assert obj.status == "degraded"

    with pytest.raises(ValidationError):
        CaptureHealthPayload(
            source="rentals_ca",
            schema_version="2026-05-07",
            status="oops",
            reason="x",
        )
```

- [ ] **Step 2.2: Run to verify failure**

Run from `apps/api/`:
```
pytest tests/capture/test_schemas.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'rentwise.capture'`.

- [ ] **Step 2.3: Implement schemas**

Create `apps/api/rentwise/capture/__init__.py` (empty file).

Create `apps/api/rentwise/capture/schemas.py`:

```python
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
    is hard-capped at 200 chars per `docs/legal.md`.
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
```

- [ ] **Step 2.4: Run tests to verify pass**

Run from `apps/api/`:
```
pytest tests/capture/test_schemas.py -v
```
Expected: PASS.

- [ ] **Step 2.5: Commit**

```
git add apps/api/rentwise/capture/__init__.py apps/api/rentwise/capture/schemas.py apps/api/tests/capture/__init__.py apps/api/tests/capture/test_schemas.py
git commit -m "feat(api): capture pydantic schemas (#21)"
```

---

## Task 3: CapturePairingRepo (singleton create / rotate)

**Files:**
- Create: `apps/api/rentwise/capture/pairing.py`
- Test: `apps/api/tests/capture/test_pairing_repo.py`

- [ ] **Step 3.1: Write the failing repo tests**

Create `apps/api/tests/capture/test_pairing_repo.py`:

```python
"""Tests for CapturePairingRepo — get-or-create singleton, rotate."""

from __future__ import annotations

import pytest

from rentwise.capture.pairing import CapturePairingRepo


@pytest.mark.asyncio
async def test_get_or_create_creates_when_absent(session):
    repo = CapturePairingRepo(session)
    record = await repo.get_or_create()
    await session.commit()

    assert record.token
    assert len(record.token) >= 32  # 32-byte secret in hex/urlsafe is >= 32 chars
    assert record.rotated_at is None


@pytest.mark.asyncio
async def test_get_or_create_is_idempotent(session):
    repo = CapturePairingRepo(session)
    first = await repo.get_or_create()
    await session.commit()
    second = await repo.get_or_create()
    await session.commit()

    assert first.token == second.token


@pytest.mark.asyncio
async def test_rotate_replaces_token_and_sets_rotated_at(session):
    repo = CapturePairingRepo(session)
    first = await repo.get_or_create()
    await session.commit()

    rotated = await repo.rotate()
    await session.commit()

    assert rotated.token != first.token
    assert rotated.rotated_at is not None


@pytest.mark.asyncio
async def test_get_returns_none_when_unset(session):
    repo = CapturePairingRepo(session)
    assert await repo.get() is None
```

- [ ] **Step 3.2: Run to verify failure**

Run from `apps/api/`:
```
pytest tests/capture/test_pairing_repo.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'rentwise.capture.pairing'`.

- [ ] **Step 3.3: Implement the repo**

Create `apps/api/rentwise/capture/pairing.py`:

```python
"""Singleton repo for the capture-pairing shared secret.

The token is generated server-side; the user pastes it into the extension's
options page. Rotation deletes-then-creates so any old token immediately
stops working.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.storage.models import CapturePairingRow


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_token() -> str:
    # 32 bytes of entropy, URL-safe base64 — fits in headers, no escaping.
    return secrets.token_urlsafe(32)


@dataclass(frozen=True)
class CapturePairing:
    token: str
    created_at: str
    rotated_at: str | None


class CapturePairingRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _row(self) -> CapturePairingRow | None:
        return (
            await self.session.execute(
                select(CapturePairingRow).where(CapturePairingRow.id == 1)
            )
        ).scalar_one_or_none()

    async def get(self) -> CapturePairing | None:
        row = await self._row()
        if row is None:
            return None
        return CapturePairing(
            token=row.token, created_at=row.created_at, rotated_at=row.rotated_at
        )

    async def get_or_create(self) -> CapturePairing:
        row = await self._row()
        if row is None:
            row = CapturePairingRow(
                id=1, token=_new_token(), created_at=_now_iso(), rotated_at=None
            )
            self.session.add(row)
            await self.session.flush()
        return CapturePairing(
            token=row.token, created_at=row.created_at, rotated_at=row.rotated_at
        )

    async def rotate(self) -> CapturePairing:
        row = await self._row()
        now = _now_iso()
        if row is None:
            row = CapturePairingRow(id=1, token=_new_token(), created_at=now, rotated_at=None)
            self.session.add(row)
        else:
            row.token = _new_token()
            row.rotated_at = now
        await self.session.flush()
        return CapturePairing(
            token=row.token, created_at=row.created_at, rotated_at=row.rotated_at
        )
```

- [ ] **Step 3.4: Run tests to verify pass**

Run from `apps/api/`:
```
pytest tests/capture/test_pairing_repo.py -v
```
Expected: PASS.

- [ ] **Step 3.5: Commit**

```
git add apps/api/rentwise/capture/pairing.py apps/api/tests/capture/test_pairing_repo.py
git commit -m "feat(api): CapturePairingRepo singleton get/rotate (#21)"
```

---

## Task 4: ListingRepo.upsert_by_source_url (null-skip + capture_method)

**Files:**
- Modify: `apps/api/rentwise/storage/repositories.py`
- Test: `apps/api/tests/storage/test_listing_upsert_by_source_url.py`

The merge rules (from spec § 6.4):
- New row → insert with `first_seen_at = captured_at`, `last_seen_at = captured_at`.
- Existing row → only overwrite fields where the new value is non-null. Always advance `last_seen_at`.
- Never overwrite `description_snippet` from a `search_results` capture (the search-card text is too short and may be misleading; only `listing_detail` provides authoritative description).
- Never replace a non-empty `photos` list with a single thumbnail from a `search_results` capture. (Detail wins for `photos`; for new rows captured at search level, `thumbnail_url` becomes the only photo until a detail capture replaces it.)
- Records `capture_method` so Phase 4 can distinguish extension- vs server-sourced rows.

- [ ] **Step 4.1: Write the failing repo tests**

Create `apps/api/tests/storage/test_listing_upsert_by_source_url.py`:

```python
"""Tests for ListingRepo.upsert_by_source_url — null-skip + detail-wins merge."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import HttpUrl

from rentwise.storage.repositories import ListingRepo


def _fields(**overrides) -> dict:
    base = {
        "source_url": HttpUrl("https://rentals.ca/listing/abc"),
        "title": "Bright 2BR",
        "price_cad": 2800,
        "bedrooms": 2.0,
        "bathrooms": None,
        "neighborhood": "Kitsilano",
        "posted_at": None,
        "photos": [],
        "description_snippet": None,
        "thumbnail_url": HttpUrl("https://rentals.ca/img/abc.jpg"),
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_upsert_inserts_new_row_with_capture_method_and_first_seen(session):
    repo = ListingRepo(session)
    captured_at = datetime.now(UTC)
    saved = await repo.upsert_by_source_url(
        source="rentals_ca",
        source_listing_id="abc",
        fields=_fields(),
        capture_method="extension",
        page_type="search_results",
        captured_at=captured_at,
    )
    await session.commit()

    fetched = await repo.get_by_source("rentals_ca", "abc")
    assert fetched is not None
    assert fetched.title == "Bright 2BR"
    assert fetched.price_cad == 2800
    assert str(saved.id) == str(fetched.id)
    # Search-results capture seeds photos from thumbnail_url
    assert [str(p) for p in fetched.photos] == ["https://rentals.ca/img/abc.jpg"]


@pytest.mark.asyncio
async def test_upsert_null_field_does_not_overwrite_existing(session):
    repo = ListingRepo(session)
    t0 = datetime.now(UTC)

    # Detail capture sets snippet
    await repo.upsert_by_source_url(
        source="rentals_ca",
        source_listing_id="abc",
        fields=_fields(description_snippet="Sunny west-facing 2BR"),
        capture_method="extension",
        page_type="listing_detail",
        captured_at=t0,
    )
    await session.commit()

    # Search-results capture without snippet must NOT clobber it
    await repo.upsert_by_source_url(
        source="rentals_ca",
        source_listing_id="abc",
        fields=_fields(description_snippet=None, price_cad=2900),
        capture_method="extension",
        page_type="search_results",
        captured_at=t0,
    )
    await session.commit()

    fetched = await repo.get_by_source("rentals_ca", "abc")
    assert fetched.description_snippet == "Sunny west-facing 2BR"
    assert fetched.price_cad == 2900  # non-null override is allowed


@pytest.mark.asyncio
async def test_search_results_capture_does_not_replace_detail_photos(session):
    repo = ListingRepo(session)
    t0 = datetime.now(UTC)

    # Detail capture seeds full photo list
    detail_photos = [
        HttpUrl("https://rentals.ca/img/abc-1.jpg"),
        HttpUrl("https://rentals.ca/img/abc-2.jpg"),
    ]
    await repo.upsert_by_source_url(
        source="rentals_ca",
        source_listing_id="abc",
        fields=_fields(photos=detail_photos, thumbnail_url=None),
        capture_method="extension",
        page_type="listing_detail",
        captured_at=t0,
    )
    await session.commit()

    # Subsequent search-results capture would otherwise downgrade to [thumbnail]
    await repo.upsert_by_source_url(
        source="rentals_ca",
        source_listing_id="abc",
        fields=_fields(
            photos=[],
            thumbnail_url=HttpUrl("https://rentals.ca/img/abc-thumb.jpg"),
        ),
        capture_method="extension",
        page_type="search_results",
        captured_at=t0,
    )
    await session.commit()

    fetched = await repo.get_by_source("rentals_ca", "abc")
    assert len(fetched.photos) == 2  # detail's photos preserved


@pytest.mark.asyncio
async def test_upsert_advances_last_seen_at(session):
    repo = ListingRepo(session)
    t0 = datetime(2026, 5, 7, 10, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 5, 7, 11, 0, 0, tzinfo=UTC)

    await repo.upsert_by_source_url(
        source="rentals_ca",
        source_listing_id="abc",
        fields=_fields(),
        capture_method="extension",
        page_type="listing_detail",
        captured_at=t0,
    )
    await session.commit()

    await repo.upsert_by_source_url(
        source="rentals_ca",
        source_listing_id="abc",
        fields=_fields(),
        capture_method="extension",
        page_type="listing_detail",
        captured_at=t1,
    )
    await session.commit()

    fetched = await repo.get_by_source("rentals_ca", "abc")
    assert fetched.last_seen_at == t1
```

- [ ] **Step 4.2: Run tests to verify failure**

Run from `apps/api/`:
```
pytest tests/storage/test_listing_upsert_by_source_url.py -v
```
Expected: FAIL — `AttributeError: 'ListingRepo' object has no attribute 'upsert_by_source_url'`.

- [ ] **Step 4.3: Implement upsert_by_source_url**

Edit `apps/api/rentwise/storage/repositories.py`. Add this method to `ListingRepo`, **and** update `_to_pydantic` so `posted_at`/`last_seen_at` round-trip through the new code path even when they were stored at the captured timestamp:

```python
# Inside ListingRepo (alongside existing upsert):
    async def upsert_by_source_url(
        self,
        *,
        source: str,
        source_listing_id: str,
        fields: dict,
        capture_method: str,
        page_type: str,
        captured_at: datetime,
    ) -> NormalizedListing:
        """Extension-driven upsert. Null-skip; detail-wins for snippet & photos.

        `fields` may contain any subset of: source_url, title, price_cad,
        bedrooms, bathrooms, neighborhood, posted_at, photos (list[HttpUrl]),
        thumbnail_url (HttpUrl | None), description_snippet.
        """
        existing_stmt = select(Listing).where(
            Listing.source == source, Listing.source_listing_id == source_listing_id
        )
        existing = (await self.session.execute(existing_stmt)).scalar_one_or_none()

        captured_iso = captured_at.isoformat()
        now = _now_iso()

        if existing is None:
            # Search-results captures seed photos from thumbnail; detail uses photos as-is.
            seed_photos = list(fields.get("photos") or [])
            if not seed_photos and fields.get("thumbnail_url") is not None:
                seed_photos = [fields["thumbnail_url"]]

            posted_at = fields.get("posted_at") or captured_at
            row = Listing(
                id=str(uuid4()),
                canonical_id=None,
                source=source,
                source_listing_id=source_listing_id,
                source_url=str(fields.get("source_url") or ""),
                title=fields.get("title") or "",
                snippet=(
                    fields.get("description_snippet")
                    if page_type == "listing_detail"
                    else None
                ),
                address_raw=None,
                address_normalized=None,
                neighborhood=fields.get("neighborhood"),
                lat=None,
                lon=None,
                bedrooms=fields.get("bedrooms"),
                bathrooms=fields.get("bathrooms"),
                price_cad=fields.get("price_cad"),
                pets_allowed=None,
                furnished=None,
                available_date=None,
                posted_at=posted_at.isoformat(),
                last_seen_at=captured_iso,
                first_seen_at=captured_iso,
                catchment_elementary=None,
                catchment_middle=None,
                catchment_secondary=None,
                photo_urls_json=json.dumps([str(u) for u in seed_photos]),
                raw_metadata_json=json.dumps({}),
                capture_method=capture_method,
                created_at=now,
                updated_at=now,
            )
            self.session.add(row)
        else:
            row = existing
            # Null-skip scalar updates.
            if (v := fields.get("source_url")) is not None:
                row.source_url = str(v)
            if (v := fields.get("title")) is not None:
                row.title = v
            if (v := fields.get("price_cad")) is not None:
                row.price_cad = v
            if (v := fields.get("bedrooms")) is not None:
                row.bedrooms = v
            if (v := fields.get("bathrooms")) is not None:
                row.bathrooms = v
            if (v := fields.get("neighborhood")) is not None:
                row.neighborhood = v
            if (v := fields.get("posted_at")) is not None:
                row.posted_at = v.isoformat()

            # Detail-wins: snippet only on listing_detail captures.
            if page_type == "listing_detail" and (
                v := fields.get("description_snippet")
            ) is not None:
                row.snippet = v

            # Detail-wins for photos: never replace an existing non-empty list
            # with a single thumbnail. On a search_results capture, only seed
            # the photos array if it's currently empty.
            new_photos = list(fields.get("photos") or [])
            if not new_photos and fields.get("thumbnail_url") is not None:
                if page_type == "search_results":
                    existing_list = json.loads(row.photo_urls_json or "[]")
                    if not existing_list:
                        new_photos = [fields["thumbnail_url"]]
            if new_photos:
                if page_type == "listing_detail":
                    row.photo_urls_json = json.dumps([str(u) for u in new_photos])
                else:  # search_results — only seed when empty (handled above)
                    row.photo_urls_json = json.dumps([str(u) for u in new_photos])

            row.last_seen_at = captured_iso
            row.capture_method = capture_method
            row.updated_at = now

        await self.session.flush()
        return _to_pydantic(row)
```

Also extend `_to_pydantic` is unaffected — `last_seen_at`/`posted_at` are already round-tripped via `datetime.fromisoformat`. No change needed there.

- [ ] **Step 4.4: Run tests to verify pass**

Run from `apps/api/`:
```
pytest tests/storage/test_listing_upsert_by_source_url.py -v
```
Expected: PASS — all four tests.

- [ ] **Step 4.5: Run the broader storage suite to confirm no regression**

Run from `apps/api/`:
```
pytest tests/storage/ -v
```
Expected: PASS.

- [ ] **Step 4.6: Commit**

```
git add apps/api/rentwise/storage/repositories.py apps/api/tests/storage/test_listing_upsert_by_source_url.py
git commit -m "feat(api): ListingRepo.upsert_by_source_url with null-skip + detail-wins (#21)"
```

---

## Task 5: Token auth + origin gating dependencies

**Files:**
- Create: `apps/api/rentwise/capture/auth.py`
- Test: `apps/api/tests/capture/test_auth.py`

- [ ] **Step 5.1: Write the failing tests**

Create `apps/api/tests/capture/test_auth.py`:

```python
"""Tests for verify_capture_token + verify_local_origin dependencies."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from rentwise.capture.auth import verify_capture_token, verify_local_origin
from rentwise.capture.pairing import CapturePairingRepo
from rentwise.storage.db import session_dep


@pytest.fixture
def app(client_with_db):
    """Borrow the migrated app fixture from test_capture_router."""
    return client_with_db.app  # provided by shared client fixture below


def _build_app(monkeypatch, tmp_sqlite_url):
    import concurrent.futures
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    monkeypatch.setenv("DATABASE_URL", tmp_sqlite_url)

    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", tmp_sqlite_url)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(command.upgrade, cfg, "head").result()

    from rentwise.storage import db as dbmod

    dbmod.get_engine.cache_clear()
    dbmod.get_sessionmaker.cache_clear()

    from rentwise.settings import settings

    settings.database_url = tmp_sqlite_url

    from rentwise.main import create_app

    return create_app()


@pytest.fixture
def client(monkeypatch, tmp_sqlite_url):
    from fastapi.testclient import TestClient

    app = _build_app(monkeypatch, tmp_sqlite_url)
    with TestClient(app) as c:
        yield c


async def test_verify_capture_token_rejects_when_unpaired(client):
    """If no pairing exists, every token is rejected with 401."""
    r = client.post(
        "/capture",
        headers={"X-RentWise-Token": "anything"},
        json={
            "source": "rentals_ca",
            "captured_at": "2026-05-07T12:00:00+00:00",
            "page_type": "search_results",
            "page_url": "https://rentals.ca/vancouver",
            "schema_version": "x",
            "listings": [],
        },
    )
    assert r.status_code == 401


async def test_verify_capture_token_rejects_wrong_token(client):
    # Pair first, then send wrong token.
    pair = client.get("/capture/pair", headers={"Origin": "http://localhost:8081"})
    assert pair.status_code == 200

    r = client.post(
        "/capture",
        headers={"X-RentWise-Token": "wrong-token"},
        json={
            "source": "rentals_ca",
            "captured_at": "2026-05-07T12:00:00+00:00",
            "page_type": "search_results",
            "page_url": "https://rentals.ca/vancouver",
            "schema_version": "x",
            "listings": [],
        },
    )
    assert r.status_code == 401


async def test_verify_capture_token_accepts_correct(client):
    pair = client.get("/capture/pair", headers={"Origin": "http://localhost:8081"})
    token = pair.json()["token"]

    r = client.post(
        "/capture",
        headers={"X-RentWise-Token": token},
        json={
            "source": "rentals_ca",
            "captured_at": "2026-05-07T12:00:00+00:00",
            "page_type": "search_results",
            "page_url": "https://rentals.ca/vancouver",
            "schema_version": "x",
            "listings": [],
        },
    )
    assert r.status_code == 200


async def test_verify_local_origin_rejects_external(client):
    r = client.get("/capture/pair", headers={"Origin": "https://evil.example.com"})
    assert r.status_code == 403


async def test_verify_local_origin_accepts_localhost(client):
    r = client.get("/capture/pair", headers={"Origin": "http://localhost:8081"})
    assert r.status_code == 200


async def test_verify_local_origin_accepts_127_0_0_1(client):
    r = client.get("/capture/pair", headers={"Origin": "http://127.0.0.1:3000"})
    assert r.status_code == 200


async def test_verify_local_origin_rejects_missing_origin(client):
    r = client.get("/capture/pair")
    assert r.status_code == 403
```

- [ ] **Step 5.2: Run to verify failure**

Run from `apps/api/`:
```
pytest tests/capture/test_auth.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'rentwise.capture.auth'`.

- [ ] **Step 5.3: Implement the dependencies**

Create `apps/api/rentwise/capture/auth.py`:

```python
"""Auth dependencies for the capture endpoints.

- `verify_capture_token` — extension → /capture, /capture/health.
  Compares `X-RentWise-Token` against the singleton secret with hmac.compare_digest.
- `verify_local_origin` — web app → /capture/pair, /capture/pair/rotate.
  Rejects any Origin that is not localhost / 127.0.0.1 / [::1] (any port).
"""

from __future__ import annotations

import hmac
from urllib.parse import urlparse

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.capture.pairing import CapturePairingRepo
from rentwise.storage.db import session_dep

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


async def verify_capture_token(
    x_rentwise_token: str | None = Header(default=None),
    session: AsyncSession = Depends(session_dep),
) -> None:
    if x_rentwise_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_token")

    repo = CapturePairingRepo(session)
    pairing = await repo.get()
    if pairing is None:
        # No secret has been generated yet — reject everything.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_paired")

    if not hmac.compare_digest(x_rentwise_token, pairing.token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad_token")


def verify_local_origin(origin: str | None = Header(default=None)) -> None:
    if origin is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="missing_origin")
    parsed = urlparse(origin)
    if parsed.hostname is None or parsed.hostname not in _LOCAL_HOSTS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="non_local_origin")
```

- [ ] **Step 5.4: Run tests after Task 6 (router) wires this up. Defer pass-verification to Task 6.**

The auth tests post to `/capture` and `/capture/pair`, which Task 6 builds. Run them at the end of Task 6.

- [ ] **Step 5.5: Commit**

```
git add apps/api/rentwise/capture/auth.py apps/api/tests/capture/test_auth.py
git commit -m "feat(api): capture auth — token compare + local-origin gate (#21)"
```

---

## Task 6: /capture/pair endpoints + main.py wiring

**Files:**
- Create: `apps/api/rentwise/capture/router.py` (initial — only the pair routes)
- Modify: `apps/api/rentwise/main.py` (register the capture router)
- Test: `apps/api/tests/capture/test_pairing_router.py`

- [ ] **Step 6.1: Write the failing pairing-router tests**

Create `apps/api/tests/capture/test_pairing_router.py`:

```python
"""Tests for /capture/pair + /capture/pair/rotate."""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command


@pytest.fixture
def client(monkeypatch, tmp_sqlite_url):
    monkeypatch.setenv("DATABASE_URL", tmp_sqlite_url)

    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", tmp_sqlite_url)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(command.upgrade, cfg, "head").result()

    from rentwise.storage import db as dbmod

    dbmod.get_engine.cache_clear()
    dbmod.get_sessionmaker.cache_clear()

    from rentwise.settings import settings

    settings.database_url = tmp_sqlite_url

    from rentwise.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


def test_pair_get_creates_token_on_first_call(client):
    r = client.get("/capture/pair", headers={"Origin": "http://localhost:8081"})
    assert r.status_code == 200
    body = r.json()
    assert "token" in body and len(body["token"]) >= 32
    assert body["server_url"].startswith("http://127.0.0.1")


def test_pair_get_returns_same_token_on_repeat(client):
    a = client.get("/capture/pair", headers={"Origin": "http://localhost:8081"}).json()
    b = client.get("/capture/pair", headers={"Origin": "http://localhost:8081"}).json()
    assert a["token"] == b["token"]


def test_pair_rotate_changes_token(client):
    a = client.get("/capture/pair", headers={"Origin": "http://localhost:8081"}).json()
    rot = client.post(
        "/capture/pair/rotate", headers={"Origin": "http://localhost:8081"}
    )
    assert rot.status_code == 200
    b = client.get("/capture/pair", headers={"Origin": "http://localhost:8081"}).json()
    assert a["token"] != b["token"]


def test_pair_blocks_external_origin(client):
    r = client.get("/capture/pair", headers={"Origin": "https://evil.example.com"})
    assert r.status_code == 403
```

- [ ] **Step 6.2: Run to verify failure**

Run from `apps/api/`:
```
pytest tests/capture/test_pairing_router.py -v
```
Expected: FAIL — 404 (router not registered).

- [ ] **Step 6.3: Implement the router with pair routes only**

Create `apps/api/rentwise/capture/router.py`:

```python
"""Capture router — extension capture + pairing endpoints."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from rentwise.capture.auth import verify_capture_token, verify_local_origin
from rentwise.capture.pairing import CapturePairingRepo
from rentwise.capture.schemas import (
    CaptureHealthPayload,
    CapturePairResponse,
    CapturePayload,
    CaptureResponse,
)
from rentwise.storage.db import session_dep

log = structlog.get_logger(__name__)


def build_router(api_base_url: str = "http://127.0.0.1:8000") -> APIRouter:
    router = APIRouter(prefix="/capture", tags=["capture"])

    @router.get(
        "/pair",
        response_model=CapturePairResponse,
        dependencies=[Depends(verify_local_origin)],
    )
    async def pair_get(
        session: AsyncSession = Depends(session_dep),
    ) -> CapturePairResponse:
        repo = CapturePairingRepo(session)
        pairing = await repo.get_or_create()
        await session.commit()
        return CapturePairResponse(token=pairing.token, server_url=api_base_url)

    @router.post(
        "/pair/rotate",
        response_model=CapturePairResponse,
        dependencies=[Depends(verify_local_origin)],
    )
    async def pair_rotate(
        session: AsyncSession = Depends(session_dep),
    ) -> CapturePairResponse:
        repo = CapturePairingRepo(session)
        pairing = await repo.rotate()
        await session.commit()
        return CapturePairResponse(token=pairing.token, server_url=api_base_url)

    return router
```

- [ ] **Step 6.4: Register the router in main.py**

Edit `apps/api/rentwise/main.py`. Add the capture router registration after the search router:

```python
    from rentwise.http.search import build_router

    app.include_router(build_router())

    from rentwise.capture.router import build_router as build_capture_router

    app.include_router(build_capture_router())
```

- [ ] **Step 6.5: Run pair-router + auth tests to verify pass**

Run from `apps/api/`:
```
pytest tests/capture/test_pairing_router.py tests/capture/test_auth.py -v
```
Expected: PASS for `test_pairing_router.py` (4 tests) and the origin-gating tests in `test_auth.py`. The `/capture` POST tests in `test_auth.py` will still fail until Task 7 — that's fine; we'll re-run after that task.

- [ ] **Step 6.6: Commit**

```
git add apps/api/rentwise/capture/router.py apps/api/rentwise/main.py apps/api/tests/capture/test_pairing_router.py
git commit -m "feat(api): /capture/pair + /capture/pair/rotate (#21)"
```

---

## Task 7: POST /capture endpoint

**Files:**
- Modify: `apps/api/rentwise/capture/router.py`
- Test: `apps/api/tests/capture/test_capture_router.py`

- [ ] **Step 7.1: Write the failing /capture tests**

Create `apps/api/tests/capture/test_capture_router.py`:

```python
"""Tests for POST /capture — auth, upsert, response counts."""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command


@pytest.fixture
def client(monkeypatch, tmp_sqlite_url):
    monkeypatch.setenv("DATABASE_URL", tmp_sqlite_url)
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", tmp_sqlite_url)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(command.upgrade, cfg, "head").result()
    from rentwise.storage import db as dbmod

    dbmod.get_engine.cache_clear()
    dbmod.get_sessionmaker.cache_clear()
    from rentwise.settings import settings

    settings.database_url = tmp_sqlite_url
    from rentwise.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


def _pair(client) -> str:
    return client.get(
        "/capture/pair", headers={"Origin": "http://localhost:8081"}
    ).json()["token"]


def _payload(**overrides) -> dict:
    base = {
        "source": "rentals_ca",
        "captured_at": "2026-05-07T12:00:00+00:00",
        "page_type": "listing_detail",
        "page_url": "https://rentals.ca/listing/abc",
        "schema_version": "2026-05-07",
        "listings": [
            {
                "source_listing_id": "abc",
                "url": "https://rentals.ca/listing/abc",
                "title": "Bright 2BR",
                "price": 2800,
                "bedrooms": 2.0,
                "neighborhood": "Kitsilano",
                "page_type": "listing_detail",
            }
        ],
    }
    base.update(overrides)
    return base


def test_capture_requires_token(client):
    _pair(client)
    r = client.post("/capture", json=_payload())
    assert r.status_code == 401


def test_capture_accepts_valid_payload(client):
    token = _pair(client)
    r = client.post("/capture", json=_payload(), headers={"X-RentWise-Token": token})
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] == 1
    assert body["skipped_duplicates"] == 0
    assert body["errors"] == []


def test_capture_empty_listings_is_ok(client):
    token = _pair(client)
    r = client.post(
        "/capture",
        json=_payload(listings=[]),
        headers={"X-RentWise-Token": token},
    )
    assert r.status_code == 200
    assert r.json()["accepted"] == 0


def test_capture_persists_listing_visible_in_db(client):
    """Capture once; the listing must be retrievable via the storage layer."""
    import asyncio

    from rentwise.storage.db import get_sessionmaker
    from rentwise.storage.repositories import ListingRepo

    token = _pair(client)
    r = client.post("/capture", json=_payload(), headers={"X-RentWise-Token": token})
    assert r.status_code == 200

    async def _fetch():
        factory = get_sessionmaker()
        async with factory() as s:
            return await ListingRepo(s).get_by_source("rentals_ca", "abc")

    fetched = asyncio.get_event_loop().run_until_complete(_fetch())
    assert fetched is not None
    assert fetched.title == "Bright 2BR"
    assert fetched.price_cad == 2800


def test_capture_re_post_advances_last_seen(client):
    token = _pair(client)
    p1 = _payload()
    p1["captured_at"] = "2026-05-07T10:00:00+00:00"
    r1 = client.post("/capture", json=p1, headers={"X-RentWise-Token": token})
    assert r1.status_code == 200

    p2 = _payload()
    p2["captured_at"] = "2026-05-07T11:00:00+00:00"
    r2 = client.post("/capture", json=p2, headers={"X-RentWise-Token": token})
    assert r2.status_code == 200
    # second call upserts the same row, accepted still 1
    assert r2.json()["accepted"] == 1


def test_capture_rejects_oversize_snippet(client):
    token = _pair(client)
    p = _payload()
    p["listings"][0]["description_snippet"] = "x" * 201
    r = client.post("/capture", json=p, headers={"X-RentWise-Token": token})
    assert r.status_code == 422  # Pydantic validation
```

- [ ] **Step 7.2: Run to verify failure**

Run from `apps/api/`:
```
pytest tests/capture/test_capture_router.py -v
```
Expected: FAIL with 404 (no /capture route yet).

- [ ] **Step 7.3: Add the /capture route**

Edit `apps/api/rentwise/capture/router.py`. Add the POST handler after the existing `pair_rotate` handler, inside `build_router`:

```python
    @router.post(
        "",
        response_model=CaptureResponse,
        dependencies=[Depends(verify_capture_token)],
    )
    async def capture(
        payload: CapturePayload,
        session: AsyncSession = Depends(session_dep),
    ) -> CaptureResponse:
        from rentwise.storage.repositories import ListingRepo

        repo = ListingRepo(session)
        accepted = 0
        errors: list[dict] = []
        for idx, item in enumerate(payload.listings):
            try:
                await repo.upsert_by_source_url(
                    source=payload.source,
                    source_listing_id=item.source_listing_id,
                    fields={
                        "source_url": str(item.url),
                        "title": item.title,
                        "price_cad": item.price,
                        "bedrooms": item.bedrooms,
                        "bathrooms": item.bathrooms,
                        "neighborhood": item.neighborhood,
                        "posted_at": item.posted_at,
                        "photos": item.photo_urls,
                        "thumbnail_url": item.thumbnail_url,
                        "description_snippet": item.description_snippet,
                    },
                    capture_method="extension",
                    page_type=item.page_type,
                    captured_at=payload.captured_at,
                )
                accepted += 1
            except Exception as exc:  # noqa: BLE001 — surface per-row error to client
                log.warning(
                    "capture_row_failed",
                    source=payload.source,
                    source_listing_id=item.source_listing_id,
                    error=str(exc),
                )
                errors.append({"index": idx, "message": str(exc)})

        try:
            await session.commit()
        except Exception as exc:
            await session.rollback()
            raise HTTPException(status_code=503, detail="storage_unavailable") from exc

        return CaptureResponse(
            accepted=accepted,
            skipped_duplicates=0,  # upsert collapses duplicates; no separate count yet
            errors=errors,
        )
```

- [ ] **Step 7.4: Run tests to verify pass**

Run from `apps/api/`:
```
pytest tests/capture/test_capture_router.py tests/capture/test_auth.py -v
```
Expected: PASS — all of `test_capture_router.py` and the `/capture` POST tests in `test_auth.py`.

- [ ] **Step 7.5: Commit**

```
git add apps/api/rentwise/capture/router.py apps/api/tests/capture/test_capture_router.py
git commit -m "feat(api): POST /capture upserts captured listings (#21)"
```

---

## Task 8: POST /capture/health

**Files:**
- Modify: `apps/api/rentwise/capture/router.py`
- Test: `apps/api/tests/capture/test_health_router.py`

- [ ] **Step 8.1: Write the failing health-router tests**

Create `apps/api/tests/capture/test_health_router.py`:

```python
"""Tests for POST /capture/health — content scripts ping when selectors break."""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command


@pytest.fixture
def client(monkeypatch, tmp_sqlite_url):
    monkeypatch.setenv("DATABASE_URL", tmp_sqlite_url)
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", tmp_sqlite_url)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(command.upgrade, cfg, "head").result()
    from rentwise.storage import db as dbmod

    dbmod.get_engine.cache_clear()
    dbmod.get_sessionmaker.cache_clear()
    from rentwise.settings import settings

    settings.database_url = tmp_sqlite_url
    from rentwise.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


def _pair(client) -> str:
    return client.get(
        "/capture/pair", headers={"Origin": "http://localhost:8081"}
    ).json()["token"]


def test_health_requires_token(client):
    _pair(client)
    r = client.post(
        "/capture/health",
        json={
            "source": "rentals_ca",
            "schema_version": "2026-05-07",
            "status": "degraded",
            "reason": "card selector missing",
        },
    )
    assert r.status_code == 401


def test_health_records_degraded_status(client):
    import asyncio

    from rentwise.storage.db import get_sessionmaker
    from rentwise.storage.repositories import SourceHealthRepo

    token = _pair(client)
    r = client.post(
        "/capture/health",
        json={
            "source": "rentals_ca",
            "schema_version": "2026-05-07",
            "status": "degraded",
            "reason": "card selector missing",
        },
        headers={"X-RentWise-Token": token},
    )
    assert r.status_code == 204

    async def _fetch():
        factory = get_sessionmaker()
        async with factory() as s:
            return await SourceHealthRepo(s).get("rentals_ca")

    health = asyncio.get_event_loop().run_until_complete(_fetch())
    assert health is not None
    assert health.status == "degraded"
    assert "card selector missing" in (health.last_error or "")
```

- [ ] **Step 8.2: Run to verify failure**

Run from `apps/api/`:
```
pytest tests/capture/test_health_router.py -v
```
Expected: FAIL with 404.

- [ ] **Step 8.3: Add the /capture/health handler**

Edit `apps/api/rentwise/capture/router.py`. Add inside `build_router`, after the `capture` handler:

```python
    @router.post(
        "/health",
        status_code=204,
        dependencies=[Depends(verify_capture_token)],
    )
    async def capture_health(
        payload: CaptureHealthPayload,
        session: AsyncSession = Depends(session_dep),
    ) -> None:
        from rentwise.storage.repositories import SourceHealthRepo

        repo = SourceHealthRepo(session)
        await repo.set(
            source=payload.source,
            status=payload.status,
            error=f"{payload.schema_version}: {payload.reason}",
        )
        try:
            await session.commit()
        except Exception as exc:
            await session.rollback()
            raise HTTPException(status_code=503, detail="storage_unavailable") from exc
        return None
```

- [ ] **Step 8.4: Run tests to verify pass**

Run from `apps/api/`:
```
pytest tests/capture/test_health_router.py -v
```
Expected: PASS — both tests.

- [ ] **Step 8.5: Commit**

```
git add apps/api/rentwise/capture/router.py apps/api/tests/capture/test_health_router.py
git commit -m "feat(api): POST /capture/health degraded ping (#21)"
```

---

## Task 9: Final lint + full suite + PR prep

- [ ] **Step 9.1: Run the full backend suite**

Run from `apps/api/`:
```
pytest -v
```
Expected: PASS — every test, including pre-existing.

- [ ] **Step 9.2: Lint + format**

Run from `apps/api/`:
```
ruff check .
ruff format .
```
Expected: no errors.

- [ ] **Step 9.3: If formatter touched files, commit**

```
git status
git add -A   # only if ruff format made changes
git commit -m "chore(api): ruff format pass (#21)"
```

- [ ] **Step 9.4: Push the branch and open the PR against main**

```
git push -u origin feat/phase-3-capture-api
gh pr create \
  --base main \
  --title "feat(api): Phase 3 PR-A — /capture endpoint, pairing, upsert (#21)" \
  --body "Closes #21. Implements the local capture API per docs/superpowers/specs/2026-05-07-phase-3-launcher-extension-design.md § 6, § 7, § 14."
```

---

## Self-Review Notes

- Spec § 6.1 (pairing flow): covered by Task 3 + Task 6.
- Spec § 6.2 (endpoints): /capture in Task 7, /capture/health in Task 8, /capture/pair + /pair/rotate in Task 6.
- Spec § 6.3 (CaptureListing schema, snippet ≤200): Task 2.
- Spec § 6.4 (upsert merge semantics): Task 4.
- Spec § 7 (migration): Task 1 — capture_method, first_seen_at, capture_pairing.
- Spec § 14 PR-A line items: all covered.
- Out-of-scope items deliberately deferred: extension scaffold (PR-B), launcher button (PR-C).
