"""Vancouver neighborhood → Forward-Sortation-Area (FSA) postal seed.

The FSA is the first three characters of a Canadian postal code; CL accepts
it as the `postal=` query parameter and combines with `search_distance=` to
build a radius search. We cap radius at ~5km in the URL builder.
"""

from __future__ import annotations

NEIGHBORHOOD_POSTAL_SEEDS: dict[str, str] = {
    "downtown": "V6B",
    "yaletown": "V6Z",
    "west end": "V6E",
    "coal harbour": "V6C",
    "gastown": "V6B",
    "chinatown": "V6A",
    "kitsilano": "V6K",
    "fairview": "V5Z",
    "mount pleasant": "V5T",
    "main street": "V5V",
    "kerrisdale": "V6N",
    "dunbar": "V6S",
    "point grey": "V6R",
    "south granville": "V6H",
    "shaughnessy": "V6H",
    "west side": "V6L",
    "marpole": "V6P",
    "oakridge": "V5Y",
    "sunset": "V5X",
    "victoria-fraserview": "V5P",
    "killarney": "V5S",
    "east vancouver": "V5L",
    "commercial drive": "V5L",
    "hastings-sunrise": "V5K",
    "renfrew": "V5M",
    "grandview-woodland": "V5N",
    "strathcona": "V6A",
    "olympic village": "V5Y",
    "south cambie": "V5Z",
    "cambie": "V5Z",
}

_ALIASES: dict[str, str] = {
    "kits": "kitsilano",
    "east van": "east vancouver",
    "the drive": "commercial drive",
    "main": "main street",
    "south van": "victoria-fraserview",
}


def normalize_neighborhood(name: str) -> str:
    n = name.strip().lower()
    return _ALIASES.get(n, n)


def seed_for(name: str) -> str | None:
    return NEIGHBORHOOD_POSTAL_SEEDS.get(normalize_neighborhood(name))
