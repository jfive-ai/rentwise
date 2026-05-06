from urllib.parse import parse_qs, urlparse

from rentwise.adapters.craigslist.url_builder import build_search_urls
from rentwise.models import NormalizedQuery


def _parse(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


def test_default_url_has_format_rss_and_haspic():
    urls = build_search_urls(NormalizedQuery(), region="vancouver")
    assert len(urls) == 1
    q = _parse(urls[0])
    assert q["format"] == ["rss"]
    assert q["hasPic"] == ["1"]


def test_price_and_bedroom_filters_set_correctly():
    q = NormalizedQuery(price_min=1500, price_max=3000, bedrooms_min=2, bedrooms_max=3)
    url = build_search_urls(q, region="vancouver")[0]
    p = _parse(url)
    assert p["min_price"] == ["1500"]
    assert p["max_price"] == ["3000"]
    assert p["min_bedrooms"] == ["2"]
    assert p["max_bedrooms"] == ["3"]


def test_keywords_become_query_param():
    q = NormalizedQuery(free_text_keywords=["pool", "rooftop"])
    p = _parse(build_search_urls(q, region="vancouver")[0])
    assert p["query"] == ["pool rooftop"]


def test_known_neighborhood_adds_postal_and_radius():
    q = NormalizedQuery(neighborhoods=["Kitsilano"])
    url = build_search_urls(q, region="vancouver")[0]
    p = _parse(url)
    assert p["postal"] == ["V6K"]
    assert p["search_distance"] == ["5"]


def test_unknown_neighborhood_dropped_and_reported():
    q = NormalizedQuery(neighborhoods=["Atlantis"])
    urls = build_search_urls(q, region="vancouver")
    p = _parse(urls[0])
    assert "postal" not in p


def test_multi_neighborhood_yields_multiple_urls_capped_at_three():
    q = NormalizedQuery(neighborhoods=["Kitsilano", "East Vancouver", "Yaletown", "Downtown"])
    urls = build_search_urls(q, region="vancouver")
    assert len(urls) == 3


def test_region_changes_subdomain():
    url = build_search_urls(NormalizedQuery(), region="seattle")[0]
    assert urlparse(url).netloc == "seattle.craigslist.org"
