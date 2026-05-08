"""Nearest-stop transit lookup.

Given a (lat, lon), finds the closest TransLink stop by haversine
distance and converts it to a walk-time using a constant pedestrian
speed (default 5 km/h). For the MVP this is good enough; real walking
networks (street graph routing, elevation, weather) are a Phase 7+
concern when we add the map view.

Stops come from a slim ``translink_stops.json`` packaged with the API.
The committed copy is a hand-authored subset — see ``data/README.md``
for how to refresh from the real GTFS feed.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from rentwise.models import TransitInfo

DEFAULT_STOPS_JSON = Path(__file__).parent / "data" / "translink_stops.json"
EARTH_RADIUS_KM = 6371.0088
DEFAULT_PEDESTRIAN_KMH = 5.0
# How far we'll consider a stop "near" before giving up — beyond this we
# return None rather than reporting a 30-minute walk to the only stop in
# the dataset.
DEFAULT_MAX_RADIUS_KM = 2.0


@dataclass(frozen=True)
class _Stop:
    name: str
    lat: float
    lon: float
    lines: tuple[str, ...]
    route_types: tuple[str, ...]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two (lat, lon) points in kilometers."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def walk_minutes(distance_km: float, *, pedestrian_kmh: float = DEFAULT_PEDESTRIAN_KMH) -> int:
    """Convert a kilometer distance to whole walk-minutes (rounded up)."""
    if distance_km <= 0:
        return 0
    return math.ceil((distance_km / pedestrian_kmh) * 60.0)


class TransitLookup:
    """Loads stops once, answers nearest-stop queries."""

    def __init__(
        self,
        *,
        stops_path: Path | None = None,
        pedestrian_kmh: float = DEFAULT_PEDESTRIAN_KMH,
        max_radius_km: float = DEFAULT_MAX_RADIUS_KM,
    ) -> None:
        self._stops: list[_Stop] = list(_load(stops_path or DEFAULT_STOPS_JSON))
        self._pedestrian_kmh = pedestrian_kmh
        self._max_radius_km = max_radius_km

    def nearest(self, lat: float | None, lon: float | None) -> TransitInfo | None:
        if lat is None or lon is None or not self._stops:
            return None
        best: tuple[_Stop, float] | None = None
        for stop in self._stops:
            d = haversine_km(lat, lon, stop.lat, stop.lon)
            if best is None or d < best[1]:
                best = (stop, d)
        if best is None or best[1] > self._max_radius_km:
            return None
        stop, distance = best
        return TransitInfo(
            nearest_stop_name=stop.name,
            walk_minutes=walk_minutes(distance, pedestrian_kmh=self._pedestrian_kmh),
            line=stop.lines[0] if stop.lines else None,
        )


def _load(path: Path) -> list[_Stop]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return []
    items = raw.get("stops", [])
    if not isinstance(items, list):
        return []
    out: list[_Stop] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            lat = float(item["lat"])
            lon = float(item["lon"])
            name = str(item["name"])
        except (KeyError, TypeError, ValueError):
            continue
        lines = tuple(str(x) for x in (item.get("lines") or []) if isinstance(x, (str, int, float)))
        route_types = tuple(str(x) for x in (item.get("route_types") or []) if isinstance(x, str))
        out.append(_Stop(name=name, lat=lat, lon=lon, lines=lines, route_types=route_types))
    return out
