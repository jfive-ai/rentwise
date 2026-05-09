"""Generate `enrichment/data/vsb_catchments.geojson` from public data.

Algorithm (#93)
---------------
The Vancouver School Board does NOT publish official catchment polygons
as open data. The committed catchment GeoJSON is therefore an
**approximation** derived from two public datasets via a deterministic
Voronoi tessellation:

1. School point locations come from the City of Vancouver Open Data
   `schools` dataset (CC-BY / Open Government Licence - Vancouver).
2. Local-area polygons (`vancouver_local_areas.geojson`, already
   committed) are unioned to produce a city-shape clipping mask.
3. `shapely.ops.voronoi_diagram` partitions the clip envelope into one
   cell per school; each cell is clipped to the Vancouver city shape.

Output is a `FeatureCollection` whose features carry:
    properties.level: "elementary" | "secondary"
    properties.name:  the school name (without the "Secondary" /
                      "Elementary" suffix — matches the LLM prompt's
                      catchment list)
    properties._source: "voronoi-from-school-points"
    properties._note:   warning that this is approximation, not
                        verbatim VSB data

Usage:
    cd apps/api
    python scripts/refresh_school_catchments.py

The committed file is regenerated from the latest school points —
re-run after refreshing `vancouver_schools.geojson`.
"""

from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import (
    MultiPoint,
    Point,
    box,
    mapping,
    shape,
)
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union, voronoi_diagram

DATA = Path(__file__).resolve().parents[1] / "rentwise" / "enrichment" / "data"
LOCAL_AREAS = DATA / "vancouver_local_areas.geojson"
SCHOOLS = DATA / "vancouver_schools.geojson"
OUT = DATA / "vsb_catchments.geojson"

# Schools to include. Names match the public dataset's `school_name`
# value (without the trailing "Secondary"/"Elementary" suffix in the
# output `name` property — that matches the LLM's catchment label list).
#
# We intentionally include only public schools. Independent / private /
# StrongStart entries skew the Voronoi cells without representing real
# catchment authority.
SECONDARY_NAMES_RAW = {
    "Britannia Community Secondary": "Britannia",
    "David Thompson Secondary": "David Thompson",
    "Eric Hamber Secondary": "Eric Hamber",
    "Gladstone Secondary": "Gladstone",
    "John Oliver Secondary": "John Oliver",
    "Killarney Secondary": "Killarney",
    "King George Secondary": "King George",
    "Kitsilano Secondary": "Kitsilano",
    "Lord Byng Secondary": "Lord Byng",
    "Magee Secondary": "Magee",
    "Point Grey Secondary": "Point Grey",
    "Prince of Wales Secondary": "Prince of Wales",
    "Sir Charles Tupper Secondary": "Sir Charles Tupper",
    "Sir Winston Churchill Secondary": "Sir Winston Churchill",
    "Templeton Secondary": "Templeton",
    "Vancouver Technical Secondary": "Vancouver Technical",
    "Windermere Community Secondary": "Windermere",
}


def _city_shape() -> BaseGeometry:
    raw = json.loads(LOCAL_AREAS.read_text(encoding="utf-8"))
    polys = [shape(f["geometry"]) for f in raw["features"] if f.get("geometry")]
    return unary_union(polys)


def _school_points(raw_to_label: dict[str, str]) -> list[tuple[str, Point]]:
    raw = json.loads(SCHOOLS.read_text(encoding="utf-8"))
    out: list[tuple[str, Point]] = []
    for feat in raw["features"]:
        props = feat.get("properties") or {}
        name = props.get("school_name")
        if name in raw_to_label:
            geo = props.get("geo_point_2d") or {}
            lon = geo.get("lon")
            lat = geo.get("lat")
            if isinstance(lon, (int, float)) and isinstance(lat, (int, float)):
                out.append((raw_to_label[name], Point(float(lon), float(lat))))
    if len(out) != len(raw_to_label):
        missing = set(raw_to_label.values()) - {n for n, _ in out}
        raise SystemExit(f"School points missing for: {sorted(missing)}")
    return out


def _voronoi_cells(
    schools: list[tuple[str, Point]], envelope: BaseGeometry
) -> list[tuple[str, BaseGeometry]]:
    pts = MultiPoint([p for _, p in schools])
    diagram = voronoi_diagram(pts, envelope=envelope.envelope)
    cells = list(diagram.geoms)
    # Map cells back to schools by which point each cell contains.
    name_by_point: dict[tuple[float, float], str] = {(p.x, p.y): n for n, p in schools}
    out: list[tuple[str, BaseGeometry]] = []
    for cell in cells:
        match: str | None = None
        for _name, p in schools:
            if cell.contains(p):
                match = name_by_point[(p.x, p.y)]
                break
        if match is None:
            # Should never happen — Voronoi guarantees one cell per point.
            continue
        clipped = cell.intersection(envelope)
        if clipped.is_empty:
            continue
        out.append((match, clipped))
    return out


def main() -> None:
    if not LOCAL_AREAS.exists():
        raise SystemExit(f"missing {LOCAL_AREAS}")
    if not SCHOOLS.exists():
        raise SystemExit(f"missing {SCHOOLS}")

    city = _city_shape()
    schools = _school_points(SECONDARY_NAMES_RAW)
    sec_envelope = box(-123.30, 49.18, -122.95, 49.32)
    sec_cells = _voronoi_cells(schools, sec_envelope.intersection(city) or city)

    features = []
    for name, geom in sec_cells:
        # MultiPolygon → GeoJSON natively; both shapes are accepted by
        # the loader. Keep the geometry as-is rather than re-projecting.
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "level": "secondary",
                    "name": name,
                    "_source": "voronoi-from-school-points",
                    "_note": (
                        "Approximation derived from City of Vancouver `schools` "
                        "dataset point locations + the city's local-area boundary. "
                        "VSB does not publish official catchment polygons as open "
                        "data. Hand-traced overrides may live above this list."
                    ),
                },
                "geometry": mapping(geom),
            }
        )

    fc = {
        "type": "FeatureCollection",
        "_source": (
            "Voronoi tessellation of public secondary-school point locations "
            "(City of Vancouver Open Data `schools` dataset), clipped to the "
            "city's local-area boundary. NOT verbatim VSB catchment polygons "
            "— see scripts/refresh_school_catchments.py for the algorithm."
        ),
        "_attribution": "Contains information licensed under the Open Government Licence - Vancouver.",
        "features": features,
    }
    OUT.write_text(json.dumps(fc, indent=2), encoding="utf-8")
    print(f"wrote {OUT} with {len(features)} secondary catchments")


if __name__ == "__main__":
    main()
