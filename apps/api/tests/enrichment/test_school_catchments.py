"""School catchment lookup tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rentwise.enrichment.school_catchments import (
    DEFAULT_GEOJSON,
    SchoolCatchmentLookup,
)


def _write_geojson(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _square(west: float, south: float, east: float, north: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [west, south],
                [east, south],
                [east, north],
                [west, north],
                [west, south],
            ]
        ],
    }


@pytest.fixture
def synthetic_geojson(tmp_path: Path) -> Path:
    """Two non-overlapping elementary cells + one big secondary cell."""
    return _write_geojson(
        tmp_path / "catchments.geojson",
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"level": "elementary", "name": "West Cell"},
                    "geometry": _square(-1.0, 0.0, 0.0, 1.0),
                },
                {
                    "type": "Feature",
                    "properties": {"level": "elementary", "name": "East Cell"},
                    "geometry": _square(0.0, 0.0, 1.0, 1.0),
                },
                {
                    "type": "Feature",
                    "properties": {"level": "secondary", "name": "Whole Area"},
                    "geometry": _square(-1.0, 0.0, 1.0, 1.0),
                },
            ],
        },
    )


def test_point_inside_returns_matching_levels(synthetic_geojson: Path) -> None:
    lookup = SchoolCatchmentLookup(geojson_path=synthetic_geojson)
    out = lookup.lookup(0.5, 0.5)  # lat=0.5, lon=0.5 → inside east + whole-area
    assert out.elementary == "East Cell"
    assert out.middle is None
    assert out.secondary == "Whole Area"


def test_point_outside_returns_empty(synthetic_geojson: Path) -> None:
    lookup = SchoolCatchmentLookup(geojson_path=synthetic_geojson)
    out = lookup.lookup(5.0, 5.0)
    assert out.elementary is None
    assert out.middle is None
    assert out.secondary is None


def test_west_cell_resolves_to_west_cell(synthetic_geojson: Path) -> None:
    lookup = SchoolCatchmentLookup(geojson_path=synthetic_geojson)
    out = lookup.lookup(0.5, -0.5)  # lat=0.5, lon=-0.5
    assert out.elementary == "West Cell"
    assert out.secondary == "Whole Area"


def test_lookup_handles_missing_coords() -> None:
    lookup = SchoolCatchmentLookup(geojson_path=DEFAULT_GEOJSON)
    assert lookup.lookup(None, None).elementary is None
    assert lookup.lookup(49.26, None).elementary is None
    assert lookup.lookup(None, -123.15).elementary is None


def test_lookup_works_against_default_fixture() -> None:
    """The committed Voronoi catchments resolve well-known addresses (#93).

    These coords are at the heart of each school's Voronoi cell — they
    should still resolve to the same school after every refresh of
    `vsb_catchments.geojson`. If a refresh changes the answer here, the
    Voronoi seed (school point) probably moved.
    """
    lookup = SchoolCatchmentLookup()  # default path
    # 4750 W 16th Ave area — Lord Byng territory.
    assert lookup.lookup(49.255, -123.185).secondary == "Lord Byng"
    # Kitsilano Secondary's neighborhood.
    assert lookup.lookup(49.262, -123.163).secondary == "Kitsilano"
    # Eric Hamber catchment near Oak/41st.
    assert lookup.lookup(49.235, -123.125).secondary == "Eric Hamber"
    # Britannia catchment around Commercial Drive.
    assert lookup.lookup(49.275, -123.07).secondary == "Britannia"


def test_loader_skips_malformed_features(tmp_path: Path) -> None:
    path = _write_geojson(
        tmp_path / "bad.geojson",
        {
            "type": "FeatureCollection",
            "features": [
                # Missing level
                {"type": "Feature", "properties": {"name": "X"}, "geometry": _square(0, 0, 1, 1)},
                # Bogus level
                {
                    "type": "Feature",
                    "properties": {"level": "preschool", "name": "Y"},
                    "geometry": _square(0, 0, 1, 1),
                },
                # No geometry
                {"type": "Feature", "properties": {"level": "elementary", "name": "Z"}},
                # Good one
                {
                    "type": "Feature",
                    "properties": {"level": "elementary", "name": "OK"},
                    "geometry": _square(0, 0, 1, 1),
                },
            ],
        },
    )
    lookup = SchoolCatchmentLookup(geojson_path=path)
    out = lookup.lookup(0.5, 0.5)
    assert out.elementary == "OK"


def test_loader_returns_empty_for_missing_file(tmp_path: Path) -> None:
    lookup = SchoolCatchmentLookup(geojson_path=tmp_path / "nope.geojson")
    out = lookup.lookup(0.5, 0.5)
    assert out.elementary is None


def test_loader_returns_empty_for_non_collection(tmp_path: Path) -> None:
    bad = tmp_path / "bad.geojson"
    bad.write_text(json.dumps({"type": "Feature", "geometry": _square(0, 0, 1, 1)}))
    lookup = SchoolCatchmentLookup(geojson_path=bad)
    assert lookup.lookup(0.5, 0.5).elementary is None
