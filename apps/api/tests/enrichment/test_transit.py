"""Transit lookup tests."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from rentwise.enrichment.transit import (
    DEFAULT_STOPS_JSON,
    TransitLookup,
    haversine_km,
    walk_minutes,
)


def _write_stops(path: Path, stops: list[dict]) -> Path:
    path.write_text(json.dumps({"stops": stops}), encoding="utf-8")
    return path


class TestHaversine:
    def test_zero_distance(self) -> None:
        assert haversine_km(49.26, -123.15, 49.26, -123.15) == 0.0

    def test_known_distance(self) -> None:
        # ~1 degree of latitude ≈ 111.2 km
        d = haversine_km(0.0, 0.0, 1.0, 0.0)
        assert math.isclose(d, 111.2, rel_tol=0.01)

    def test_symmetric(self) -> None:
        a = haversine_km(49.26, -123.15, 49.27, -123.16)
        b = haversine_km(49.27, -123.16, 49.26, -123.15)
        assert math.isclose(a, b)


class TestWalkMinutes:
    def test_zero_distance_is_zero_minutes(self) -> None:
        assert walk_minutes(0.0) == 0

    def test_one_kilometer_at_5_kmh(self) -> None:
        # 1 km / 5 km/h = 12 minutes
        assert walk_minutes(1.0, pedestrian_kmh=5.0) == 12

    def test_round_up(self) -> None:
        # 0.5 km / 5 km/h = 6 minutes; 0.51 km should round up to 7
        assert walk_minutes(0.51, pedestrian_kmh=5.0) == 7


class TestTransitLookup:
    @pytest.fixture
    def two_stop_file(self, tmp_path: Path) -> Path:
        return _write_stops(
            tmp_path / "stops.json",
            [
                {
                    "name": "Alpha Stn",
                    "lat": 49.260,
                    "lon": -123.100,
                    "lines": ["X"],
                    "route_types": ["skytrain"],
                },
                {
                    "name": "Beta Stn",
                    "lat": 49.270,
                    "lon": -123.150,
                    "lines": ["Y"],
                    "route_types": ["skytrain"],
                },
            ],
        )

    def test_returns_nearest(self, two_stop_file: Path) -> None:
        lookup = TransitLookup(stops_path=two_stop_file, max_radius_km=10.0)
        # Closer to Beta Stn
        info = lookup.nearest(49.272, -123.151)
        assert info is not None
        assert info.nearest_stop_name == "Beta Stn"
        assert info.walk_minutes >= 0
        assert info.line == "Y"

    def test_returns_none_for_missing_coords(self, two_stop_file: Path) -> None:
        lookup = TransitLookup(stops_path=two_stop_file)
        assert lookup.nearest(None, None) is None
        assert lookup.nearest(49.26, None) is None
        assert lookup.nearest(None, -123.15) is None

    def test_respects_max_radius(self, two_stop_file: Path) -> None:
        lookup = TransitLookup(stops_path=two_stop_file, max_radius_km=0.001)
        # Far from any stop relative to the ridiculously small radius.
        assert lookup.nearest(49.20, -123.20) is None

    def test_returns_none_when_dataset_empty(self, tmp_path: Path) -> None:
        empty = _write_stops(tmp_path / "empty.json", [])
        lookup = TransitLookup(stops_path=empty)
        assert lookup.nearest(49.26, -123.15) is None

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        lookup = TransitLookup(stops_path=tmp_path / "nope.json")
        assert lookup.nearest(49.26, -123.15) is None

    def test_skips_malformed_entries(self, tmp_path: Path) -> None:
        path = _write_stops(
            tmp_path / "mixed.json",
            [
                {"name": "Good", "lat": 49.260, "lon": -123.100},
                {"name": "Bad", "lat": "not-a-number", "lon": -123.100},
                {"lat": 49.260, "lon": -123.100},  # missing name
                "string-not-an-object",
            ],
        )
        lookup = TransitLookup(stops_path=path, max_radius_km=10.0)
        info = lookup.nearest(49.260, -123.100)
        assert info is not None
        assert info.nearest_stop_name == "Good"


def test_default_stops_file_loads() -> None:
    """The committed synthetic stops.json must round-trip — sanity check."""
    lookup = TransitLookup(stops_path=DEFAULT_STOPS_JSON, max_radius_km=10.0)
    # Broadway-City Hall Station is at ~49.2630, -123.1140; query nearby.
    info = lookup.nearest(49.263, -123.115)
    assert info is not None
    assert info.nearest_stop_name == "Broadway-City Hall Station"
    assert info.line == "Canada Line"
