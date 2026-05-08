"""Perceptual hashing for cross-source dedup.

Fetches the listing's primary photo URL once, computes a 64-bit
``imagehash.phash``, discards the image bytes, and caches the hex hash
keyed by URL. The cache is what keeps subsequent searches cheap — we
never re-download an image we've already hashed.

Per ``docs/legal.md`` § 4: photo URLs may be stored, photo bytes may
not. The bytes live in memory only for the duration of the hash; we
never write them to disk.
"""

from __future__ import annotations

import io
from typing import Protocol

import httpx
import imagehash
import structlog
from PIL import Image, UnidentifiedImageError

log = structlog.get_logger(__name__)

# Cap to keep us from accidentally streaming a 50 MB studio photo into
# memory. 8 MB is plenty for typical rental thumbnails.
MAX_IMAGE_BYTES = 8 * 1024 * 1024


class PhotoHasher(Protocol):
    """Minimal protocol so tests can swap in a fake."""

    async def hash_url(self, url: str) -> str | None:
        """Return the hex pHash for ``url``, or ``None`` on failure."""
        ...


class HttpxPhotoHasher:
    """Production hasher: fetch with httpx, hash with imagehash."""

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_seconds: float = 5.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._user_agent = user_agent
        self._timeout = timeout_seconds
        self._client = client
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def hash_url(self, url: str) -> str | None:
        if not url.strip():
            return None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            try:
                resp = await client.get(
                    url,
                    headers={"User-Agent": self._user_agent},
                    follow_redirects=True,
                )
                resp.raise_for_status()
            except (TimeoutError, httpx.HTTPError) as exc:
                log.info("photo_hash.fetch_failed", url=url, error=str(exc))
                return None
            content = resp.content
            if len(content) > MAX_IMAGE_BYTES:
                log.info("photo_hash.too_large", url=url, size=len(content))
                return None
            return _compute_phash(content)
        finally:
            if self._client is None:
                await client.aclose()


def _compute_phash(image_bytes: bytes) -> str | None:
    """Decode bytes → PIL.Image → imagehash.phash → hex string. None on failure."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            # Convert to RGB so phash is robust to alpha-channel quirks.
            rgb = img.convert("RGB")
            h = imagehash.phash(rgb)
            return str(h)  # imagehash's __str__ produces a 16-char hex
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        log.info("photo_hash.decode_failed", error=str(exc))
        return None


def hamming_distance(a: str | None, b: str | None) -> int | None:
    """Hamming distance between two hex pHashes. None if either input is missing/invalid."""
    if not a or not b:
        return None
    try:
        ha = imagehash.hex_to_hash(a)
        hb = imagehash.hex_to_hash(b)
    except (ValueError, TypeError):
        return None
    diff = ha - hb
    return int(diff)
