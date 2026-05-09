"""Tests for the Phase 1 model additions."""

from datetime import UTC, datetime

from rentwise.models import (
    AdapterHealth,
    NormalizedListing,
    NormalizedQuery,
    SchoolCatchments,
    SearchRequest,
    SearchResponse,
    SortOrder,
)


def test_school_catchments_defaults_all_none():
    sc = SchoolCatchments()
    assert sc.elementary is None
    assert sc.middle is None
    assert sc.secondary is None


def test_normalized_listing_school_catchments_is_object_not_list():
    listing = NormalizedListing(
        canonical_id="00000000-0000-0000-0000-000000000000",
        source="craigslist",
        source_url="https://example.com/x",
        source_listing_id="x",
        title="t",
        address=None,
        address_normalized=None,
        lat=None,
        lon=None,
        bedrooms=None,
        bathrooms=None,
        price_cad=None,
        pets_allowed=None,
        furnished=None,
        available_date=None,
        posted_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
        photos=[],
        description_snippet=None,
    )
    assert isinstance(listing.school_catchments, SchoolCatchments)


def test_search_request_defaults():
    req = SearchRequest(query=NormalizedQuery())
    assert req.force_refresh is False
    assert req.limit == 50
    assert req.offset == 0
    assert req.sort == SortOrder.NEWEST


def test_search_response_contract():
    resp = SearchResponse(
        listings=[],
        total=0,
        cache_status="miss",
        unsupported_filters=["pets"],
        source_health={"craigslist": AdapterHealth(name="craigslist", status="ok")},
    )
    assert resp.total == 0
    assert resp.unsupported_filters == ["pets"]
    assert resp.source_health["craigslist"].status == "ok"


def test_sort_order_values():
    assert {s.value for s in SortOrder} == {
        "newest",
        "price_asc",
        "price_desc",
        "bedrooms_asc",
        "bedrooms_desc",
        # Legacy alias kept for already-shared URLs.
        "bedrooms",
        "title_asc",
        "title_desc",
        "source_asc",
        "source_desc",
    }
