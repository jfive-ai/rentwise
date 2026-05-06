"""Property tests for url_builder.build_search_urls."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from hypothesis import given
from hypothesis import strategies as st

from rentwise.adapters.craigslist.url_builder import build_search_urls
from rentwise.models import NormalizedQuery

_ALLOWED_PARAMS = {
    "format",
    "hasPic",
    "min_price",
    "max_price",
    "min_bedrooms",
    "max_bedrooms",
    "query",
    "postal",
    "search_distance",
}


@pytest.mark.property
@given(
    bmin=st.one_of(st.none(), st.integers(min_value=0, max_value=10)),
    bmax=st.one_of(st.none(), st.integers(min_value=0, max_value=10)),
    pmin=st.one_of(st.none(), st.integers(min_value=0, max_value=10000)),
    pmax=st.one_of(st.none(), st.integers(min_value=0, max_value=10000)),
    kw=st.lists(st.text(min_size=0, max_size=10), max_size=4),
    nbhds=st.lists(
        st.sampled_from(["Kitsilano", "East Vancouver", "Atlantis", "Yaletown", "Downtown"]),
        max_size=5,
    ),
)
def test_only_known_params_appear(bmin, bmax, pmin, pmax, kw, nbhds):
    q = NormalizedQuery(
        bedrooms_min=bmin,
        bedrooms_max=bmax,
        price_min=pmin,
        price_max=pmax,
        free_text_keywords=kw,
        neighborhoods=nbhds,
    )
    for url in build_search_urls(q, region="vancouver"):
        params = parse_qs(urlparse(url).query)
        assert set(params.keys()) <= _ALLOWED_PARAMS
        for key, values in params.items():
            assert len(values) == 1, f"duplicate key {key}"
