"""Vancouver School Board catchment lookup.

Loads polygons from a GeoJSON file (default:
``enrichment/data/vsb_catchments.geojson``) and answers point-in-polygon
queries that return per-level catchment names.

The committed GeoJSON is **synthetic** — see ``data/README.md`` for how
to refresh it from real VSB shapefiles. The loader is agnostic to where
the polygons came from as long as the schema invariants hold:

- top level is a ``FeatureCollection``
- each feature has a ``Polygon`` geometry in WGS84 (EPSG:4326)
- each feature has ``properties.level`` ∈ {elementary, middle, secondary}
- each feature has ``properties.name`` (the catchment's display name)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry

from rentwise.models import SchoolCatchments

CatchmentLevel = Literal["elementary", "middle", "secondary"]
_VALID_LEVELS: set[str] = {"elementary", "middle", "secondary"}

DEFAULT_GEOJSON = Path(__file__).parent / "data" / "vsb_catchments.geojson"


@dataclass(frozen=True)
class _Catchment:
    level: CatchmentLevel
    name: str
    geom: BaseGeometry


class SchoolCatchmentLookup:
    """Loads a VSB catchments GeoJSON file once, answers point queries.

    Construct one of these per process — the polygon list is small but
    parsing happens once on init.
    """

    def __init__(self, *, geojson_path: Path | None = None) -> None:
        self._catchments: list[_Catchment] = list(_load(geojson_path or DEFAULT_GEOJSON))

    def lookup(self, lat: float | None, lon: float | None) -> SchoolCatchments:
        """Return per-level catchments containing ``(lat, lon)``.

        Returns an empty :class:`SchoolCatchments` if either coord is
        missing or no polygon contains the point. If multiple polygons of
        the same level overlap (shouldn't happen with real VSB data —
        catchments tile the city), the first one wins.
        """
        if lat is None or lon is None:
            return SchoolCatchments()
        point = Point(lon, lat)  # shapely uses (x, y) = (lon, lat)
        elementary: str | None = None
        middle: str | None = None
        secondary: str | None = None
        for c in self._catchments:
            if not c.geom.contains(point):
                continue
            if c.level == "elementary" and elementary is None:
                elementary = c.name
            elif c.level == "middle" and middle is None:
                middle = c.name
            elif c.level == "secondary" and secondary is None:
                secondary = c.name
        return SchoolCatchments(
            elementary=elementary,
            middle=middle,
            secondary=secondary,
        )


def _load(path: Path) -> list[_Catchment]:
    """Parse the GeoJSON file. Skips malformed features rather than failing
    the whole process — a single bad polygon shouldn't kill enrichment."""
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("type") != "FeatureCollection":
        return []
    features = raw.get("features", [])
    if not isinstance(features, list):
        return []
    out: list[_Catchment] = []
    for feat in features:
        if not isinstance(feat, dict):
            continue
        props = feat.get("properties") or {}
        level = props.get("level")
        name = props.get("name")
        geom_dict = feat.get("geometry")
        if level not in _VALID_LEVELS or not isinstance(name, str) or geom_dict is None:
            continue
        try:
            geom = shape(geom_dict)
        except Exception:
            continue
        out.append(_Catchment(level=level, name=name, geom=geom))
    return out
