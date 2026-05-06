"""Property tests for aggregator.freshness cache_key and canonical_query_json."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from rentwise.aggregator.freshness import cache_key, canonical_query_json
from rentwise.models import NormalizedQuery

_query_st = st.builds(
    NormalizedQuery,
    bedrooms_min=st.one_of(st.none(), st.floats(min_value=0, max_value=9, allow_nan=False)),
    price_min=st.one_of(st.none(), st.integers(min_value=0, max_value=99999)),
    price_max=st.one_of(st.none(), st.integers(min_value=0, max_value=99999)),
    free_text_keywords=st.lists(st.text(max_size=15), max_size=4),
)


@pytest.mark.property
@given(q=_query_st)
def test_canonical_json_deterministic(q):
    assert canonical_query_json(q) == canonical_query_json(q)


@pytest.mark.property
@given(q1=_query_st, q2=_query_st)
def test_cache_key_iff_equality(q1, q2):
    if q1 == q2:
        assert cache_key(q1) == cache_key(q2)
    else:
        # not strictly required but a useful collision check on this scale
        if cache_key(q1) == cache_key(q2):
            assert canonical_query_json(q1) == canonical_query_json(q2)
