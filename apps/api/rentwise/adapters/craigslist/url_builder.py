"""NormalizedQuery → list of Craigslist search URLs."""

from __future__ import annotations

from urllib.parse import urlencode

from rentwise.adapters.craigslist.neighborhoods import seed_for
from rentwise.models import NormalizedQuery

_PATH = "/search/apa"
_DEFAULT_RADIUS_KM = 5
_MAX_NEIGHBORHOOD_FANOUT = 3


def build_search_urls(query: NormalizedQuery, *, region: str) -> list[str]:
    base = f"https://{region}.craigslist.org{_PATH}"
    common: dict[str, str | int] = {"format": "rss", "hasPic": 1}

    if query.price_min is not None:
        common["min_price"] = query.price_min
    if query.price_max is not None:
        common["max_price"] = query.price_max
    if query.bedrooms_min is not None:
        common["min_bedrooms"] = int(query.bedrooms_min)
    if query.bedrooms_max is not None:
        common["max_bedrooms"] = int(query.bedrooms_max)
    if query.free_text_keywords:
        common["query"] = " ".join(query.free_text_keywords)

    seeds = [s for n in query.neighborhoods if (s := seed_for(n))]
    seeds = seeds[:_MAX_NEIGHBORHOOD_FANOUT]

    if not seeds:
        return [f"{base}?{urlencode(common)}"]

    urls: list[str] = []
    for seed in seeds:
        params = dict(common)
        params["postal"] = seed
        params["search_distance"] = _DEFAULT_RADIUS_KM
        urls.append(f"{base}?{urlencode(params)}")
    return urls
