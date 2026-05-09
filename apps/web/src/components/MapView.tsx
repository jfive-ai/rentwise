/**
 * Phase 7 PR-A / PR-B: web-only MapLibre view of `NormalizedListing`s.
 *
 * Native (iOS / macOS) builds render a placeholder; the native map
 * lands alongside Phase 8.
 *
 * The map source of truth is owned by the caller (`SearchScreen`):
 * we accept the listing array + view callbacks and never mutate
 * shared state directly. The `maplibre-gl` Map instance lives in a
 * `useEffect` so re-renders don't recreate the GL context.
 *
 * PR-B adds:
 * - `selectedListingId` + `onHoverListing` for split-view selection sync.
 * - `overlays` toggles for VSB catchments + SkyTrain station radii;
 *   data is lazy-fetched from the backend `/map/overlays/*` endpoints.
 */

import Constants from "expo-constants";
import maplibregl, { type Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";
import type { NormalizedListing } from "@/src/api/types";
import {
  type Bbox,
  bboxesDiffer,
  featureCollection,
  listingsToFeatures,
} from "@/src/lib/mapClusters";
import { expandNeighborhoodNames } from "@/src/lib/neighborhoods";
import { useTheme } from "@/src/theme";

const VANCOUVER_CENTER: [number, number] = [-123.12, 49.28];
const DEFAULT_ZOOM = 11;
const SOURCE_ID = "rentwise-listings";
const CLUSTER_LAYER = "rentwise-clusters";
const CLUSTER_COUNT_LAYER = "rentwise-cluster-count";
const POINT_LAYER = "rentwise-points";

const CATCHMENTS_SOURCE = "rentwise-catchments";
const CATCHMENTS_FILL_LAYER = "rentwise-catchments-fill";
const CATCHMENTS_LINE_LAYER = "rentwise-catchments-line";
const SKYTRAIN_SOURCE = "rentwise-skytrain";
const SKYTRAIN_LAYER = "rentwise-skytrain-radii";

const NEIGHBORHOODS_SOURCE = "rentwise-neighborhoods";
const NEIGHBORHOODS_FILL_LAYER = "rentwise-neighborhoods-fill";
const NEIGHBORHOODS_LINE_LAYER = "rentwise-neighborhoods-line";

export interface MapOverlaysToggle {
  catchments: boolean;
  skytrain: boolean;
}

interface Props {
  listings: NormalizedListing[];
  onSelectListing: (id: string) => void;
  /** Fired when the user clicks "Search this area"; the bbox encodes
   * the visible viewport for the caller to re-run /search with. */
  onSearchBbox: (bbox: Bbox) => void;
  /** Phase 7 PR-B: split-view sync. */
  selectedListingId?: string | null;
  onHoverListing?: (id: string | null) => void;
  /** Phase 7 PR-B: overlay layer toggles. Lazy-fetched on first
   * enable; the backend caches with a 24h max-age. */
  overlays?: MapOverlaysToggle;
  onToggleOverlay?: (key: keyof MapOverlaysToggle) => void;
  /** Required when any overlay is enabled — same shape as the
   * `apiBaseUrl` SearchScreen receives. */
  apiBaseUrl?: string;
  /** Names the user filtered on (e.g. ["Dunbar"]). When present, the
   * matching City of Vancouver local-area polygons are highlighted on
   * the map so the user can see exactly where the post-filter is
   * confining results (#92). Free-form aliases are accepted; resolution
   * to official names happens client-side. */
  selectedNeighborhoods?: string[];
}

export function MapView(props: Props) {
  const t = useTheme();

  // Native: render the polite placeholder; never instantiate MapLibre
  // (it ships a WebGL hard dependency).
  if (Platform.OS !== "web") {
    return (
      <View style={[styles.placeholder, { borderColor: t.border, backgroundColor: t.surface }]}>
        <Text style={{ color: t.textMuted, textAlign: "center" }}>
          Map view is web-only for the MVP. The native map ships in Phase 8.
        </Text>
      </View>
    );
  }
  return <MapViewWeb {...props} />;
}

function MapViewWeb({
  listings,
  onSelectListing,
  onSearchBbox,
  selectedListingId = null,
  onHoverListing,
  overlays = { catchments: false, skytrain: false },
  onToggleOverlay,
  apiBaseUrl,
  selectedNeighborhoods,
}: Props) {
  const t = useTheme();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  // Latest listing index in a ref so the click handler we attach to
  // the map (once) always sees fresh data.
  const idIndexRef = useRef<Map<string, NormalizedListing>>(new Map());
  const [moved, setMoved] = useState(false);
  const initialBboxRef = useRef<Bbox | null>(null);
  const mapLoadedRef = useRef(false);
  // Cache of fetched overlay data so we never refetch in a session.
  const overlayCacheRef = useRef<{
    catchments?: GeoJSON.FeatureCollection | null;
    skytrain?: SkytrainStop[] | null;
    neighborhoods?: GeoJSON.FeatureCollection | null;
  }>({});

  const { features, dropped } = useMemo(
    () => listingsToFeatures(listings),
    [listings],
  );

  useEffect(() => {
    idIndexRef.current = new Map(listings.map((l) => [l.id, l]));
  }, [listings]);

  // Mount the map exactly once.
  useEffect(() => {
    if (mapRef.current || !containerRef.current) return;

    const tilesUrl =
      (Constants.expoConfig?.extra?.mapTilesUrl as string | undefined)
      ?? "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
    const attribution =
      (Constants.expoConfig?.extra?.mapTilesAttribution as string | undefined)
      ?? "© OpenStreetMap contributors";

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: [tilesUrl],
            tileSize: 256,
            attribution,
          },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
      center: VANCOUVER_CENTER,
      zoom: DEFAULT_ZOOM,
    });
    mapRef.current = map;

    map.on("load", () => {
      mapLoadedRef.current = true;
      // Catchments + skytrain sources are added empty; the toggle
      // effect below populates + renders layers when first enabled.
      map.addSource(CATCHMENTS_SOURCE, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addSource(SKYTRAIN_SOURCE, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addSource(NEIGHBORHOODS_SOURCE, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      map.addSource(SOURCE_ID, {
        type: "geojson",
        data: featureCollection([]),
        cluster: true,
        clusterRadius: 60,
        clusterMaxZoom: 14,
      });

      // Selected neighborhood — drawn under everything else so the
      // listing markers and catchment overlays still read clearly.
      // Visibility starts hidden; the toggle effect below shows it as
      // soon as the caller passes a non-empty `selectedNeighborhoods`.
      map.addLayer({
        id: NEIGHBORHOODS_FILL_LAYER,
        type: "fill",
        source: NEIGHBORHOODS_SOURCE,
        layout: { visibility: "none" },
        paint: { "fill-color": "#f97316", "fill-opacity": 0.18 },
      });
      map.addLayer({
        id: NEIGHBORHOODS_LINE_LAYER,
        type: "line",
        source: NEIGHBORHOODS_SOURCE,
        layout: { visibility: "none" },
        paint: {
          "line-color": "#ea580c",
          "line-opacity": 0.8,
          "line-width": 2,
        },
      });

      // Catchment polygons — drawn under listing markers so a marker
      // is never hidden under a polygon fill.
      map.addLayer({
        id: CATCHMENTS_FILL_LAYER,
        type: "fill",
        source: CATCHMENTS_SOURCE,
        layout: { visibility: "none" },
        paint: { "fill-color": "#16a34a", "fill-opacity": 0.12 },
      });
      map.addLayer({
        id: CATCHMENTS_LINE_LAYER,
        type: "line",
        source: CATCHMENTS_SOURCE,
        layout: { visibility: "none" },
        paint: {
          "line-color": "#16a34a",
          "line-opacity": 0.5,
          "line-width": 1.5,
        },
      });
      // SkyTrain radii — circles at fixed pixel size so they read at
      // every zoom; rough walkable-buffer.
      map.addLayer({
        id: SKYTRAIN_LAYER,
        type: "circle",
        source: SKYTRAIN_SOURCE,
        layout: { visibility: "none" },
        paint: {
          "circle-color": "#7c3aed",
          "circle-opacity": 0.15,
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            10, 8,
            14, 28,
            16, 60,
          ],
          "circle-stroke-color": "#7c3aed",
          "circle-stroke-opacity": 0.6,
          "circle-stroke-width": 1.5,
        },
      });

      map.addLayer({
        id: CLUSTER_LAYER,
        type: "circle",
        source: SOURCE_ID,
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#2563eb",
          "circle-opacity": 0.85,
          "circle-radius": [
            "step", ["get", "point_count"],
            16, 10, 22, 30, 28,
          ],
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
        },
      });
      map.addLayer({
        id: CLUSTER_COUNT_LAYER,
        type: "symbol",
        source: SOURCE_ID,
        filter: ["has", "point_count"],
        layout: {
          "text-field": "{point_count_abbreviated}",
          "text-size": 12,
        },
        paint: { "text-color": "#ffffff" },
      });
      map.addLayer({
        id: POINT_LAYER,
        type: "circle",
        source: SOURCE_ID,
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": [
            "case",
            ["==", ["get", "id"], ["literal", ""]],
            "#dc2626",
            "#1d4ed8",
          ],
          "circle-radius": [
            "case",
            ["==", ["get", "id"], ["literal", ""]],
            12,
            8,
          ],
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
        },
      });

      map.on("click", POINT_LAYER, (e) => {
        const feat = e.features?.[0];
        const id = feat?.properties?.id;
        if (typeof id === "string") onSelectListing(id);
      });
      map.on("click", CLUSTER_LAYER, (e) => {
        const feat = e.features?.[0];
        if (!feat) return;
        const clusterId = feat.properties?.cluster_id;
        const src = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
        if (!src || typeof clusterId !== "number") return;
        src.getClusterExpansionZoom(clusterId).then((zoom) => {
          const geom = feat.geometry;
          if (geom.type === "Point") {
            map.easeTo({
              center: geom.coordinates as [number, number],
              zoom,
            });
          }
        });
      });
      if (onHoverListing) {
        map.on("mousemove", POINT_LAYER, (e) => {
          const id = e.features?.[0]?.properties?.id;
          onHoverListing(typeof id === "string" ? id : null);
        });
        map.on("mouseleave", POINT_LAYER, () => onHoverListing(null));
      }

      const bounds = map.getBounds();
      initialBboxRef.current = [
        bounds.getWest(),
        bounds.getSouth(),
        bounds.getEast(),
        bounds.getNorth(),
      ];

      map.on("moveend", () => {
        const b = map.getBounds();
        const next: Bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
        if (initialBboxRef.current && bboxesDiffer(initialBboxRef.current, next)) {
          setMoved(true);
        }
      });
    });

    return () => {
      map.remove();
      mapRef.current = null;
      mapLoadedRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Push fresh features whenever the listing array changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const src = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    if (src) src.setData(featureCollection(features));
  }, [features]);

  // Highlight the selected listing — the POINT_LAYER paint expression
  // keys off `["==", ["get", "id"], ["literal", selectedId]]`. We
  // re-set the paint when the selection changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoadedRef.current) return;
    const id = selectedListingId ?? "";
    map.setPaintProperty(POINT_LAYER, "circle-color", [
      "case",
      ["==", ["get", "id"], ["literal", id]],
      "#dc2626",
      "#1d4ed8",
    ]);
    map.setPaintProperty(POINT_LAYER, "circle-radius", [
      "case",
      ["==", ["get", "id"], ["literal", id]],
      12,
      8,
    ]);
  }, [selectedListingId]);

  // Catchments overlay — fetch once, toggle layer visibility per props.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoadedRef.current) return;
    const visibility = overlays.catchments ? "visible" : "none";
    map.setLayoutProperty(CATCHMENTS_FILL_LAYER, "visibility", visibility);
    map.setLayoutProperty(CATCHMENTS_LINE_LAYER, "visibility", visibility);
    if (!overlays.catchments) return;
    if (overlayCacheRef.current.catchments !== undefined) return; // already fetched
    if (!apiBaseUrl) return;
    void fetch(`${apiBaseUrl.replace(/\/$/, "")}/map/overlays/catchments`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data: GeoJSON.FeatureCollection | null) => {
        overlayCacheRef.current.catchments = data;
        const src = map.getSource(CATCHMENTS_SOURCE) as
          | maplibregl.GeoJSONSource
          | undefined;
        if (src && data) src.setData(data);
      })
      .catch(() => {
        overlayCacheRef.current.catchments = null;
      });
  }, [overlays.catchments, apiBaseUrl]);

  // Selected-neighborhood overlay (#92). When the user filters by
  // neighborhood, fetch the full city polygon set once and filter
  // client-side to the requested names so the map highlights the same
  // polygons the backend post-filter is using.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoadedRef.current) return;
    const names = selectedNeighborhoods ?? [];
    const visibility = names.length > 0 ? "visible" : "none";
    map.setLayoutProperty(NEIGHBORHOODS_FILL_LAYER, "visibility", visibility);
    map.setLayoutProperty(NEIGHBORHOODS_LINE_LAYER, "visibility", visibility);
    if (names.length === 0) return;
    if (!apiBaseUrl) return;
    const apply = (full: GeoJSON.FeatureCollection | null) => {
      if (!full) return;
      const wanted = new Set(
        expandNeighborhoodNames(names).map((n) => n.toLowerCase()),
      );
      const filtered: GeoJSON.FeatureCollection = {
        type: "FeatureCollection",
        features: full.features.filter((f) => {
          const raw = (f.properties as { name?: string } | null)?.name;
          return typeof raw === "string" && wanted.has(raw.toLowerCase());
        }),
      };
      const src = map.getSource(NEIGHBORHOODS_SOURCE) as
        | maplibregl.GeoJSONSource
        | undefined;
      if (src) src.setData(filtered);
    };
    if (overlayCacheRef.current.neighborhoods !== undefined) {
      apply(overlayCacheRef.current.neighborhoods);
      return;
    }
    void fetch(`${apiBaseUrl.replace(/\/$/, "")}/map/overlays/neighborhoods`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data: GeoJSON.FeatureCollection | null) => {
        overlayCacheRef.current.neighborhoods = data;
        apply(data);
      })
      .catch(() => {
        overlayCacheRef.current.neighborhoods = null;
      });
  }, [selectedNeighborhoods, apiBaseUrl]);

  // Skytrain overlay — fetch once, render as point features for the
  // radii circle layer.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoadedRef.current) return;
    const visibility = overlays.skytrain ? "visible" : "none";
    map.setLayoutProperty(SKYTRAIN_LAYER, "visibility", visibility);
    if (!overlays.skytrain) return;
    if (overlayCacheRef.current.skytrain !== undefined) return;
    if (!apiBaseUrl) return;
    void fetch(`${apiBaseUrl.replace(/\/$/, "")}/map/overlays/skytrain-stops`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data: { stops: SkytrainStop[] } | null) => {
        const stops = data?.stops ?? [];
        overlayCacheRef.current.skytrain = stops;
        const fc: GeoJSON.FeatureCollection<GeoJSON.Point> = {
          type: "FeatureCollection",
          features: stops
            .filter(
              (s) => Number.isFinite(s.lat) && Number.isFinite(s.lon),
            )
            .map((s) => ({
              type: "Feature",
              geometry: { type: "Point", coordinates: [s.lon, s.lat] },
              properties: { name: s.name },
            })),
        };
        const src = map.getSource(SKYTRAIN_SOURCE) as
          | maplibregl.GeoJSONSource
          | undefined;
        if (src) src.setData(fc);
      })
      .catch(() => {
        overlayCacheRef.current.skytrain = null;
      });
  }, [overlays.skytrain, apiBaseUrl]);

  const onSearchHere = () => {
    const map = mapRef.current;
    if (!map) return;
    const b = map.getBounds();
    const bbox: Bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
    onSearchBbox(bbox);
    initialBboxRef.current = bbox;
    setMoved(false);
  };

  return (
    <View style={styles.wrap} testID="rentwise-map">
      <div
        ref={(el) => {
          containerRef.current = el;
        }}
        style={styles.canvas as React.CSSProperties}
      />
      {onToggleOverlay && (
        <View style={styles.overlayToggles}>
          <OverlayToggle
            label={`Catchments${overlays.catchments ? " ✓" : ""}`}
            active={overlays.catchments}
            accessibilityLabel="Toggle school catchments overlay"
            onPress={() => onToggleOverlay("catchments")}
          />
          <OverlayToggle
            label={`SkyTrain${overlays.skytrain ? " ✓" : ""}`}
            active={overlays.skytrain}
            accessibilityLabel="Toggle skytrain radii overlay"
            onPress={() => onToggleOverlay("skytrain")}
          />
        </View>
      )}
      {moved && (
        <View style={styles.searchHere}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Search this area"
            onPress={onSearchHere}
            style={[styles.searchBtn, { backgroundColor: t.accent }]}
          >
            <Text style={{ color: "#fff", fontWeight: "600" }}>
              Search this area
            </Text>
          </Pressable>
        </View>
      )}
      {dropped > 0 && (
        <View style={[styles.footer, { backgroundColor: t.surface }]}>
          <Text style={{ color: t.textMuted, fontSize: 12 }}>
            {dropped} listing{dropped === 1 ? "" : "s"} have no location and aren&apos;t shown.
          </Text>
        </View>
      )}
    </View>
  );
}

interface SkytrainStop {
  name: string;
  lat: number;
  lon: number;
  lines?: string[];
  route_types?: string[];
}

function OverlayToggle({
  label,
  active,
  accessibilityLabel,
  onPress,
}: {
  label: string;
  active: boolean;
  accessibilityLabel: string;
  onPress: () => void;
}) {
  const t = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      onPress={onPress}
      style={[
        styles.toggle,
        {
          backgroundColor: active ? t.accent : t.surface,
          borderColor: t.border,
        },
      ]}
    >
      <Text style={{ color: active ? "#fff" : t.text, fontSize: 12 }}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, minHeight: 480, position: "relative" },
  canvas: { position: "absolute", inset: 0, borderRadius: 8 },
  placeholder: {
    flex: 1,
    minHeight: 240,
    padding: 24,
    borderWidth: 1,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
  },
  searchHere: {
    position: "absolute",
    top: 12,
    left: "50%",
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    transform: [{ translateX: -90 } as any],
  },
  searchBtn: {
    paddingHorizontal: 18,
    paddingVertical: 10,
    borderRadius: 999,
    minWidth: 180,
    alignItems: "center",
  },
  footer: {
    position: "absolute",
    bottom: 8,
    left: 8,
    right: 8,
    padding: 8,
    borderRadius: 6,
  },
  overlayToggles: {
    position: "absolute",
    top: 12,
    right: 12,
    gap: 4,
  },
  toggle: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderWidth: 1,
    borderRadius: 6,
  },
});
