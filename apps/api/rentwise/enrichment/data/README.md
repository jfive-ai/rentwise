# Enrichment data files

These files are loaded at runtime by `enrichment/school_catchments.py`
and `enrichment/transit.py`. The committed copies are **synthetic** —
hand-authored covering a few representative Vancouver neighborhoods so
the unit tests are self-contained and CI never has to fetch external
data.

For real-world production use, refresh both files from the upstream
sources below. This is a **manual maintainer task**, not an automated
job — per the project's TOS posture (`docs/legal.md`) we don't
auto-fetch external data.

## Refreshing `vsb_catchments.geojson`

Source: Vancouver School Board (VSB) catchment shapefiles.

1. Download the elementary and secondary catchment shapefiles from
   the [VSB GIS open data portal](https://www.vsb.bc.ca/) (or the
   Vancouver Open Data portal — search for "school catchment").
2. Convert each shapefile to GeoJSON and merge into one
   `FeatureCollection` whose features have the properties
   `level` (`"elementary"` | `"middle"` | `"secondary"`) and
   `name` (e.g. `"Lord Byng"`).

   ```bash
   ogr2ogr -f GeoJSON -t_srs EPSG:4326 elementary.geojson VSB_Elementary.shp
   ogr2ogr -f GeoJSON -t_srs EPSG:4326 secondary.geojson  VSB_Secondary.shp
   ```

   Then merge with `jq` or a quick Python script that adds the
   `level` / `name` properties expected by the loader.
3. Verify the resulting file is in WGS84 (EPSG:4326). The loader
   assumes lat/lon coordinates.
4. Replace this file and run `pytest tests/enrichment` to make sure
   the catchment unit tests still pass with the new shape.

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
