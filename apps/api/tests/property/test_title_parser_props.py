"""Property tests for title_parser.parse_title."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from rentwise.adapters.craigslist.title_parser import parse_title


@pytest.mark.property
@given(s=st.text(max_size=300))
def test_parse_title_never_raises_and_satisfies_bounds(s):
    r = parse_title(s)
    if r.price_cad is not None:
        assert 100 <= r.price_cad <= 99999
    if r.bedrooms is not None:
        assert r.bedrooms in {0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0}
    if r.sqft is not None:
        assert 10 <= r.sqft <= 99999
