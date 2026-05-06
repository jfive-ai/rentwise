from pathlib import Path

import feedparser

from rentwise.adapters.craigslist.rss_parser import parse_entry

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "craigslist" / "sample_feed.rss"


def _entries():
    return feedparser.parse(FIXTURE.read_bytes()).entries


def test_first_entry_full_extraction():
    e = _entries()[0]
    raw = parse_entry(e)
    assert raw is not None
    assert raw.source == "craigslist"
    assert raw.source_listing_id == "7700000001"
    assert raw.price_cad == 2800
    assert raw.bedrooms == 2.0
    assert raw.lat == 49.2734
    assert raw.lon == -123.1631
    assert raw.description_snippet and "balcony" in raw.description_snippet


def test_snippet_is_truncated_to_200():
    e = _entries()[1]
    raw = parse_entry(e)
    assert raw is not None
    assert raw.description_snippet is not None
    assert len(raw.description_snippet) <= 200


def test_geo_optional():
    e = _entries()[1]
    raw = parse_entry(e)
    assert raw is not None
    assert raw.lat is None and raw.lon is None


def test_unparseable_post_id_returns_none():
    """If we can't extract a numeric listing id from the URL, drop the entry."""
    bad = type("E", (), {})()
    bad.title = "x"
    bad.link = "https://vancouver.craigslist.org/garbage"
    bad.summary = "x"
    bad.dc_date = "2026-05-01T00:00:00-07:00"
    assert parse_entry(bad) is None
