"""Vancouver local-area (neighborhood) lookup.

Loads the City of Vancouver Open Data ``local-area-boundary`` GeoJSON and
answers two questions:

1. ``lookup(lat, lon) -> str | None`` — which official local area does
   this point fall in? Used during enrichment to populate
   :attr:`NormalizedListing.neighborhood`.
2. ``polygons_for_query(names) -> list[BaseGeometry]`` — given a list of
   user-typed names (English or alias), resolve to the official
   polygons. Used by the aggregator's post-filter step to drop listings
   outside the requested neighborhood.

The committed GeoJSON is **real** Vancouver Open Data (Open Government
Licence - Vancouver), not synthetic. See ``data/README.md`` for the refresh
procedure.

Aliases live in ``_NEIGHBORHOOD_ALIASES`` so common search terms map onto
official names — e.g. ``Dunbar`` → ``Dunbar-Southlands``,
``Point Grey`` → ``West Point Grey``. The official name itself always
matches (case-insensitive).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry

DEFAULT_GEOJSON = Path(__file__).parent / "data" / "vancouver_local_areas.geojson"

# Common search aliases → the official local-area name.
#
# The right-hand side MUST exactly match a feature ``properties.name`` in
# the GeoJSON, otherwise resolution silently drops the alias.
#
# All keys are stored lowercased and stripped; the resolver applies the
# same normalization to the input. We intentionally do NOT alias entries
# whose *only* meaning is ambiguous (e.g. "south" — could mean Sunset,
# Marpole, or Victoria-Fraserview).
_NEIGHBORHOOD_ALIASES: dict[str, str] = {
    # Dunbar — the city's polygon is "Dunbar-Southlands". Most users say
    # just "Dunbar" and mean this entire polygon.
    "dunbar": "Dunbar-Southlands",
    "southlands": "Dunbar-Southlands",
    # West Point Grey is the user-perceived "Point Grey" neighborhood.
    "point grey": "West Point Grey",
    "pt grey": "West Point Grey",
    # Kits short form.
    "kits": "Kitsilano",
    # Several common east-side aliases.
    "the drive": "Grandview-Woodland",
    "commercial drive": "Grandview-Woodland",
    "main street": "Mount Pleasant",
    "main": "Mount Pleasant",
    "olympic village": "Mount Pleasant",
    "false creek": "Mount Pleasant",
    # "Cambie" colloquially refers to the Cambie corridor, which spans
    # South Cambie + Riley Park; we send it to South Cambie since that
    # name is the canonical real-estate identifier.
    "cambie": "South Cambie",
    # Sub-neighborhoods of Downtown — Vancouver's official local-area set
    # rolls these all into "Downtown". The polygon is wider than the
    # user-perceived sub-area but every listing inside the alias's
    # commonly-understood boundary will land in the same polygon, so
    # nothing is wrongly *excluded*. We accept the over-inclusion as a
    # known trade-off (#92).
    "yaletown": "Downtown",
    "coal harbour": "Downtown",
    "gastown": "Downtown",
    "chinatown": "Strathcona",
    # Sub-neighborhoods on the west side.
    "south granville": "Fairview",
    # "East Vancouver" is a multi-area umbrella term — we treat it as
    # the union of all east-of-Main local areas. The resolver fans out
    # via :data:`_UMBRELLA_TERMS`.
    "east van": "_EAST_VAN",
    "east vancouver": "_EAST_VAN",
    # West-side umbrella.
    "west side": "_WEST_SIDE",
    "westside": "_WEST_SIDE",
}

_UMBRELLA_TERMS: dict[str, frozenset[str]] = {
    "_EAST_VAN": frozenset(
        {
            "Grandview-Woodland",
            "Hastings-Sunrise",
            "Kensington-Cedar Cottage",
            "Killarney",
            "Mount Pleasant",
            "Renfrew-Collingwood",
            "Riley Park",
            "Strathcona",
            "Sunset",
            "Victoria-Fraserview",
        }
    ),
    "_WEST_SIDE": frozenset(
        {
            "Arbutus Ridge",
            "Dunbar-Southlands",
            "Fairview",
            "Kerrisdale",
            "Kitsilano",
            "Marpole",
            "Oakridge",
            "Shaughnessy",
            "South Cambie",
            "West Point Grey",
        }
    ),
}


@dataclass(frozen=True)
class _Area:
    name: str
    geom: BaseGeometry


class NeighborhoodLookup:
    """Loads Vancouver local-area polygons once, answers point + name queries.

    Construct one of these per process — parsing happens once on init.
    """

    def __init__(self, *, geojson_path: Path | None = None) -> None:
        self._areas: list[_Area] = list(_load(geojson_path or DEFAULT_GEOJSON))
        self._by_name: dict[str, _Area] = {a.name.casefold(): a for a in self._areas}

    @property
    def names(self) -> list[str]:
        return [a.name for a in self._areas]

    def lookup(self, lat: float | None, lon: float | None) -> str | None:
        """Return the official local-area name containing ``(lat, lon)``.

        Returns ``None`` if either coord is missing or no polygon covers
        the point (e.g. the listing is in Burnaby / Richmond / Coquitlam).

        Uses ``covers`` rather than ``contains`` so points exactly on a
        polygon boundary are still attributed to that polygon (Codex
        review #97). Two adjacent polygons sharing a boundary will both
        cover an on-boundary point — the iteration order picks the first
        match, which is stable across runs because GeoJSON feature order
        is preserved.
        """
        if lat is None or lon is None:
            return None
        point = Point(lon, lat)
        for a in self._areas:
            if a.geom.covers(point):
                return a.name
        return None

    def resolve(self, names: Iterable[str]) -> list[str]:
        """Resolve user-typed names → official local-area names.

        Order is preserved; duplicates are de-duped while preserving the
        first occurrence. Unknown names are dropped silently (the caller
        already shows a chip the user clicked, so blowing up here would
        ruin the search).
        """
        out: list[str] = []
        seen: set[str] = set()

        def _add(name: str) -> None:
            if name in seen:
                return
            seen.add(name)
            out.append(name)

        for raw in names:
            key = raw.strip().casefold()
            if not key:
                continue
            # Alias may map to a real name OR an umbrella sentinel.
            mapped = _NEIGHBORHOOD_ALIASES.get(key)
            if mapped is not None and mapped.startswith("_"):
                for member in sorted(_UMBRELLA_TERMS.get(mapped, frozenset())):
                    if member.casefold() in self._by_name:
                        _add(member)
                continue
            target_key = (mapped or raw).strip().casefold()
            area = self._by_name.get(target_key)
            if area is not None:
                _add(area.name)
        return out

    def polygons_for(self, names: Iterable[str]) -> list[BaseGeometry]:
        """Resolve `names` → list of polygons, or [] if nothing resolved."""
        official = self.resolve(names)
        return [self._by_name[n.casefold()].geom for n in official]

    def is_inside_any(
        self,
        lat: float | None,
        lon: float | None,
        names: Iterable[str],
    ) -> bool:
        """True iff `(lat, lon)` is inside the union of polygons for `names`.

        Returns ``False`` for missing coords (the caller decides whether
        to keep or drop those — same posture as transit-walk filtering).
        ``covers`` is boundary-inclusive (Codex review #97).
        """
        if lat is None or lon is None:
            return False
        point = Point(lon, lat)
        for poly in self.polygons_for(names):
            if poly.covers(point):
                return True
        return False


def _load(path: Path) -> list[_Area]:
    """Parse the GeoJSON file. Skips malformed features rather than
    failing the whole process — a single bad polygon should not kill
    enrichment."""
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("type") != "FeatureCollection":
        return []
    features = raw.get("features", [])
    if not isinstance(features, list):
        return []
    out: list[_Area] = []
    for feat in features:
        if not isinstance(feat, dict):
            continue
        props = feat.get("properties") or {}
        name = props.get("name")
        geom_dict = feat.get("geometry")
        if not isinstance(name, str) or geom_dict is None:
            continue
        try:
            geom = shape(geom_dict)
        except Exception:
            continue
        out.append(_Area(name=name, geom=geom))
    return out
