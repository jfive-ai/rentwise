"""Photo hashing tests — uses respx to mock all HTTP, real PIL/imagehash."""

from __future__ import annotations

import io

import httpx
import pytest
import respx
from PIL import Image

from rentwise.enrichment.photo_hash import (
    HttpxPhotoHasher,
    _compute_phash,
    hamming_distance,
)


def _png_bytes(
    width: int = 32, height: int = 32, color: tuple[int, int, int] = (200, 0, 0)
) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Pure-function tests
# ---------------------------------------------------------------------------


class TestComputePhash:
    def test_returns_hex_for_valid_image(self) -> None:
        out = _compute_phash(_png_bytes())
        assert isinstance(out, str)
        # imagehash phash defaults to 8x8 = 64 bits = 16 hex chars
        assert len(out) == 16

    def test_returns_none_for_garbage(self) -> None:
        assert _compute_phash(b"not an image") is None

    def test_identical_images_have_identical_hash(self) -> None:
        a = _compute_phash(_png_bytes(color=(123, 45, 67)))
        b = _compute_phash(_png_bytes(color=(123, 45, 67)))
        assert a == b


class TestHammingDistance:
    def test_zero_for_identical(self) -> None:
        h = _compute_phash(_png_bytes(color=(50, 50, 50)))
        assert hamming_distance(h, h) == 0

    def test_none_for_missing_inputs(self) -> None:
        assert hamming_distance(None, "abc") is None
        assert hamming_distance("abc", None) is None
        assert hamming_distance(None, None) is None
        assert hamming_distance("", "abc") is None

    def test_none_for_invalid_hex(self) -> None:
        assert hamming_distance("not-hex", "abc") is None


# ---------------------------------------------------------------------------
# HttpxPhotoHasher
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hash_url_returns_hex_on_success() -> None:
    png = _png_bytes()
    async with httpx.AsyncClient() as client:
        with respx.mock(assert_all_called=False) as r:
            r.get("https://example.com/photo.jpg").mock(
                return_value=httpx.Response(200, content=png, headers={"content-type": "image/png"})
            )
            hasher = HttpxPhotoHasher(user_agent="TestAgent/1.0", client=client)
            out = await hasher.hash_url("https://example.com/photo.jpg")
        assert out is not None
        assert len(out) == 16


@pytest.mark.asyncio
async def test_hash_url_returns_none_on_blank_url() -> None:
    hasher = HttpxPhotoHasher(user_agent="TestAgent/1.0")
    assert await hasher.hash_url("") is None
    assert await hasher.hash_url("   ") is None


@pytest.mark.asyncio
async def test_hash_url_returns_none_on_http_error() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(assert_all_called=False) as r:
            r.get("https://example.com/photo.jpg").mock(return_value=httpx.Response(404))
            hasher = HttpxPhotoHasher(user_agent="TestAgent/1.0", client=client)
            assert await hasher.hash_url("https://example.com/photo.jpg") is None


@pytest.mark.asyncio
async def test_hash_url_returns_none_on_unreadable_response() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(assert_all_called=False) as r:
            r.get("https://example.com/photo.jpg").mock(
                return_value=httpx.Response(200, content=b"not a real image"),
            )
            hasher = HttpxPhotoHasher(user_agent="TestAgent/1.0", client=client)
            assert await hasher.hash_url("https://example.com/photo.jpg") is None


@pytest.mark.asyncio
async def test_hash_url_skips_oversized_response() -> None:
    big = b"\x00" * (9 * 1024 * 1024)  # 9 MB > 8 MB cap
    async with httpx.AsyncClient() as client:
        with respx.mock(assert_all_called=False) as r:
            r.get("https://example.com/big.jpg").mock(return_value=httpx.Response(200, content=big))
            hasher = HttpxPhotoHasher(user_agent="TestAgent/1.0", client=client)
            assert await hasher.hash_url("https://example.com/big.jpg") is None
