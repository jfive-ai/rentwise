# Enrichment data files

These files are loaded at runtime by `enrichment/school_catchments.py`,
`enrichment/transit.py`, and `enrichment/neighborhoods.py`. They split
into three groups:

- **Real, committed**: `vancouver_local_areas.geojson` and
  `vancouver_schools.geojson` are official City of Vancouver Open Data
  (Open Government Licence – Vancouver). These rarely need refreshing.
- **Derived, committed**: `vsb_catchments.geojson` is a Voronoi
  approximation generated from `vancouver_schools.geojson` by
  `apps/api/scripts/refresh_school_catchments.py`. The Vancouver School
  Board does not publish official catchment polygons as open data, so
  Voronoi-from-public-school-points is the most defensible
  approximation we can ship from public sources alone.
- **Synthetic, committed**: `translink_stops.json` is a hand-authored
  placeholder so the unit tests stay self-contained and CI never has
  to fetch external data.

For real-world production use, refresh the derived / synthetic files
from the upstream sources below. This is a **manual maintainer task**,
not an automated job — per the project's TOS posture
(`docs/operational-rules.md`) we don't auto-fetch external data.

## Refreshing `vancouver_local_areas.geojson`

Source: City of Vancouver Open Data — `local-area-boundary` dataset
(<https://opendata.vancouver.ca/explore/dataset/local-area-boundary/>),
licensed under the [Open Government Licence – Vancouver](https://opendata.vancouver.ca/page/licence/).
Boundaries follow street centrelines and the City notes they are
stable over time, so this file rarely needs refreshing.

```bash
curl -s 'https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/local-area-boundary/exports/geojson' \
  -o apps/api/rentwise/enrichment/data/vancouver_local_areas.geojson
```

The schema invariant the loader assumes:

- top-level is a `FeatureCollection`
- each feature has a polygon geometry in WGS84 (EPSG:4326)
- each feature has `properties.name` matching one of the official 22
  local areas (`Dunbar-Southlands`, `West Point Grey`, `Kitsilano`, etc.)

If the City re-publishes with a different `name` field, update the
alias map in `enrichment/neighborhoods.py` rather than munging this
file — the alias resolver is the right place for "what the user typed
→ official name".

## Refreshing `vancouver_schools.geojson`

Source: City of Vancouver Open Data — `schools` dataset
(<https://opendata.vancouver.ca/explore/dataset/schools/>), Open
Government Licence – Vancouver. Used to derive catchments via Voronoi.

```bash
curl -s 'https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/schools/exports/geojson' \
  -o apps/api/rentwise/enrichment/data/vancouver_schools.geojson
```

After refreshing, regenerate the catchment file:

```bash
cd apps/api && python scripts/refresh_school_catchments.py
```

## Refreshing `vsb_catchments.geojson` (#93)

Generated, not edited by hand:

```bash
cd apps/api && python scripts/refresh_school_catchments.py
```

The script reads `vancouver_local_areas.geojson` and
`vancouver_schools.geojson`, computes a Voronoi tessellation of
public secondary-school points clipped to the city boundary, and
writes the result. Each feature carries `_source: "voronoi-from-school-points"`
and a `_note` explaining the approximation — the file is **not** an
authoritative VSB catchment map; it is a deterministic, public-data
approximation that's significantly better than keyword matching.

## Refreshing `translink_stops.json`

Source: [TransLink GTFS feed](https://www.translink.ca/about-us/doing-business-with-translink/app-developer-resources/gtfs).

1. Download the GTFS bundle (`google_transit.zip`) and unzip.
2. Slim it down to the fields we use:

   ```python
   import csv, json
   stops = list(csv.DictReader(open("stops.txt")))
   trips = list(csv.DictReader(open("trips.txt")))
   routes = {r["route_id"]: r for r in csv.DictReader(open("routes.txt"))}
   stop_times = list(csv.DictReader(open("stop_times.txt")))

   # Build stop_id → set of route line names + GTFS route_type
   stop_to_routes: dict[str, set[tuple[str, str]]] = {}
   trip_route = {t["trip_id"]: t["route_id"] for t in trips}
   for st in stop_times:
       route = routes.get(trip_route.get(st["trip_id"], ""))
       if route is None:
           continue
       lines = route["route_short_name"] or route["route_long_name"]
       rt = {"0": "tram", "1": "subway", "2": "rail", "3": "bus"}.get(
           route["route_type"], route["route_type"]
       )
       stop_to_routes.setdefault(st["stop_id"], set()).add((lines, rt))

   out = []
   for s in stops:
       lines_rt = stop_to_routes.get(s["stop_id"], set())
       out.append({
           "stop_id": s["stop_id"],
           "name": s["stop_name"],
           "lat": float(s["stop_lat"]),
           "lon": float(s["stop_lon"]),
           "lines": sorted({line for line, _ in lines_rt}),
           "route_types": sorted({rt for _, rt in lines_rt}),
       })
   json.dump({"stops": out}, open("translink_stops.json", "w"))
   ```

3. The full Vancouver region has ~8 000 stops at ~50 KB / 100 stops
   so the slim file lands at a few MB — fine to commit. If you want
   to keep the repo lean, filter to a Vancouver bounding box first.
4. Replace this file and run `pytest tests/enrichment/test_transit.py`
   to confirm the loader still works.

## Schema invariants the loaders assume

- `vsb_catchments.geojson`: a `FeatureCollection`; each feature has a
  `Polygon` geometry in WGS84 and the properties `level` and `name`.
- `translink_stops.json`: an object with `"stops"` → list of objects
  having `lat`, `lon`, `name`, optional `lines` (list of str), and
  optional `route_types` (list of str). Extra fields are ignored.

If you change either schema, update the loader in lockstep.
