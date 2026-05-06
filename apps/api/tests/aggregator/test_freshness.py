from datetime import UTC, datetime, timedelta

from rentwise.aggregator.freshness import cache_key, canonical_query_json, is_fresh
from rentwise.models import NormalizedQuery


def test_canonical_json_is_dict_order_independent():
    q1 = NormalizedQuery(price_min=1000, bedrooms_min=2)
    q2 = NormalizedQuery(bedrooms_min=2, price_min=1000)
    assert canonical_query_json(q1) == canonical_query_json(q2)


def test_cache_key_deterministic():
    q = NormalizedQuery(price_max=2500, free_text_keywords=["pool"])
    assert cache_key(q) == cache_key(q)


def test_cache_key_changes_with_query():
    a = NormalizedQuery(price_max=2500)
    b = NormalizedQuery(price_max=2600)
    assert cache_key(a) != cache_key(b)


def test_is_fresh_true_within_ttl():
    now = datetime.now(UTC)
    ts = (now - timedelta(seconds=10)).isoformat()
    assert is_fresh(ts, ttl_seconds=900, now=now) is True


def test_is_fresh_false_past_ttl():
    now = datetime.now(UTC)
    ts = (now - timedelta(seconds=901)).isoformat()
    assert is_fresh(ts, ttl_seconds=900, now=now) is False
