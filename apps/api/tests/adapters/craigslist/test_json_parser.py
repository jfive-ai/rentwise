"""Tests for the /jsonsearch/apa entry parser."""

from __future__ import annotations

from datetime import UTC, datetime

from rentwise.adapters.craigslist.json_parser import parse_entry


def _entry(**overrides):
    base = {
        "PostingID": 7932994841,
        "PostingURL": "https://vancouver.craigslist.org/nvn/apa/d/north-vancouver-bedroom-basement-grand/7932994841.html",
        "PostingTitle": "2 bedroom basement Grand Boulevard Moodyville short walk Lonsdale",
        "PostedDate": 1778261303,
        "Latitude": 49.310626,
        "Longitude": -123.061471,
        "bedrooms": 2,
        "price": 2450,
        "ImageThumb": "https://images.craigslist.org/00404_b0iz2k3ubzC_0630ae_50x50c.jpg",
        "CategoryID": 1,
    }
    base.update(overrides)
    return base


def test_happy_path_maps_all_core_fields():
    raw = parse_entry(_entry())
    assert raw is not None
    assert raw.source == "craigslist"
    assert raw.source_listing_id == "7932994841"
    assert str(raw.source_url).endswith("/7932994841.html")
    assert raw.title.startswith("2 bedroom basement")
    assert raw.bedrooms == 2.0
    assert raw.price_cad == 2450
    assert raw.lat == 49.310626
    assert raw.lon == -123.061471
    # Fields the JSON doesn't expose are explicitly None — we don't
    # invent them.
    assert raw.address is None
    assert raw.bathrooms is None
    assert raw.pets_allowed is None
    assert raw.furnished is None


def test_posted_date_unix_seconds_to_aware_utc_datetime():
    raw = parse_entry(_entry(PostedDate=1700000000))
    assert raw is not None
    assert raw.posted_at == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)


def test_missing_url_returns_none():
    assert parse_entry(_entry(PostingURL=None)) is None
    assert parse_entry(_entry(PostingURL="")) is None


def test_missing_id_returns_none():
    no_id = _entry()
    no_id.pop("PostingID")
    assert parse_entry(no_id) is None


def test_non_dict_returns_none():
    assert parse_entry(None) is None
    assert parse_entry([]) is None
    assert parse_entry("string") is None


def test_structured_bedrooms_and_price_win_over_title_regex():
    """Phase 1 inferred bedrooms+price by regex on the title; the JSON
    endpoint provides them as structured fields. Use the structured ones —
    they're authoritative."""
    raw = parse_entry(
        _entry(
            PostingTitle="$9999 / 5br - palace",  # regex would say price=9999, beds=5
            bedrooms=1,
            price=1500,
        )
    )
    assert raw is not None
    assert raw.bedrooms == 1.0
    assert raw.price_cad == 1500


def test_falls_back_to_title_parser_when_structured_fields_missing():
    raw = parse_entry(_entry(PostingTitle="$2750 / 2br - 800ft²", bedrooms=None, price=None))
    assert raw is not None
    assert raw.bedrooms == 2.0
    assert raw.price_cad == 2750


def test_invalid_lat_lon_become_none_not_crash():
    raw = parse_entry(_entry(Latitude="not-a-number", Longitude=None))
    assert raw is not None
    assert raw.lat is None
    assert raw.lon is None


def test_image_thumb_preserved_in_raw_metadata():
    raw = parse_entry(_entry())
    assert raw is not None
    assert raw.raw_metadata.get("image_thumb_url", "").endswith("_50x50c.jpg")


def test_far_future_timestamp_falls_back_to_now_without_raising():
    """Defensive — Pydantic's posted_at is an aware datetime; an
    out-of-range unix ts mustn't crash the entire search."""
    raw = parse_entry(_entry(PostedDate=10**15))
    assert raw is not None
    # parsed time is "now" (aware UTC) on overflow
    assert raw.posted_at.tzinfo is not None
