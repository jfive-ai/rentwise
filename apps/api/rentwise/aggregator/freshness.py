"""Cache-key derivation and TTL math.

`canonical_query_json` is the single source of truth for "are these two
queries equivalent?". Tests depend on its determinism — don't change without
adding a test.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from rentwise.models import NormalizedQuery


def canonical_query_json(query: NormalizedQuery) -> str:
    return json.dumps(
        query.model_dump(mode="json", exclude_none=False),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def cache_key(query: NormalizedQuery) -> str:
    return hashlib.sha256(canonical_query_json(query).encode("utf-8")).hexdigest()


def is_fresh(timestamp_iso: str, ttl_seconds: int, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    ts = datetime.fromisoformat(timestamp_iso)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return (now - ts).total_seconds() < ttl_seconds
