"""GET /map/overlays/{catchments,skytrain-stops} (Phase 7 PR-B).

Serves the same GeoJSON / stops data the server-side enrichment uses,
so the web map's overlays stay in sync with the catchments + transit
the backend filters on. The map fetches these endpoints once per
session (cache headers) so a refresh of the underlying data files
reaches both layers without a frontend redeploy.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Response

from rentwise.enrichment.school_catchments import DEFAULT_GEOJSON
from rentwise.enrichment.transit import DEFAULT_STOPS_JSON

# 24h cache. The data files only change on a manual refresh from the
# upstream sources (VSB shapefiles, TransLink GTFS); the browser can
# safely hold them for a day.
CACHE_HEADERS = {"Cache-Control": "public, max-age=86400"}


def build_router() -> APIRouter:
    router = APIRouter(prefix="/map/overlays", tags=["map"])

    @router.get("/catchments")
    async def get_catchments() -> Response:
        """Returns the VSB catchment FeatureCollection as raw GeoJSON."""
        if not DEFAULT_GEOJSON.exists():
            raise HTTPException(status_code=503, detail="catchments_unavailable")
        return Response(
            content=DEFAULT_GEOJSON.read_bytes(),
            media_type="application/geo+json",
            headers=CACHE_HEADERS,
        )

    @router.get("/skytrain-stops")
    async def get_skytrain_stops() -> Response:
        """Returns the TransLink stops file filtered to skytrain-only.

        Bus-only stops are dropped — they'd clutter the map without
        adding much (the SkyTrain radii are the useful overlay; bus
        coverage is dense everywhere in Vancouver).
        """
        if not DEFAULT_STOPS_JSON.exists():
            raise HTTPException(status_code=503, detail="stops_unavailable")
        raw = json.loads(DEFAULT_STOPS_JSON.read_text(encoding="utf-8"))
        stops = raw.get("stops", []) if isinstance(raw, dict) else []
        skytrain_stops = [
            s
            for s in stops
            if isinstance(s, dict)
            and isinstance(s.get("route_types"), list)
            and "skytrain" in s["route_types"]
        ]
        body = json.dumps({"stops": skytrain_stops}).encode("utf-8")
        return Response(
            content=body,
            media_type="application/json",
            headers=CACHE_HEADERS,
        )

    return router
