"""NormalizedQuery → list of Craigslist /jsonsearch/apa URLs.

Phase 1 originally targeted `/search/apa?format=rss`. As of 2026-05 that
endpoint returns 403 to unauthenticated requests (verified directly from
the project author's residential IP, three User-Agents, with and without
the `cl_b` cookie dance). The HTML page and the `/jsonsearch/apa` JSON
endpoint both still serve from the same IP, so the adapter switched to
JSON. Filter parameters are unchanged (`min_bedrooms`, `max_price`,
`postal`, `search_distance`, `query`).
"""

from __future__ import annotations

from urllib.parse import urlencode

from rentwise.adapters.craigslist.neighborhoods import seed_for
from rentwise.models import NormalizedQuery

_PATH = "/jsonsearch/apa"
_DEFAULT_RADIUS_KM = 5
_MAX_NEIGHBORHOOD_FANOUT = 3


def build_search_urls(query: NormalizedQuery, *, region: str) -> list[str]:
    base = f"https://{region}.craigslist.org{_PATH}"
    # Note: `format=rss` and `hasPic=1` are gone. The JSON endpoint
    # always returns the same shape, and `hasPic` filtered listings
    # without a thumbnail — which we now keep so the user sees the full
    # set (the UI handles missing photos gracefully).
    common: dict[str, str | int] = {}

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
        return [f"{base}?{urlencode(common)}" if common else base]

    urls: list[str] = []
    for seed in seeds:
        params = dict(common)
        params["postal"] = seed
        params["search_distance"] = _DEFAULT_RADIUS_KM
        urls.append(f"{base}?{urlencode(params)}")
    return urls
