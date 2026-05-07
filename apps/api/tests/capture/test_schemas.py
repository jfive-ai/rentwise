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
            schema_version="x",
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
