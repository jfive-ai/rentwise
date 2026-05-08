/**
 * Phase 7 PR-A: web-only MapLibre view of `NormalizedListing`s.
 *
 * Native (iOS / macOS) builds render a placeholder; the native map
 * lands alongside Phase 8.
 *
 * The map source of truth is owned by the caller (`SearchScreen`):
 * we accept the listing array + view callbacks and never mutate
 * shared state directly. The `maplibre-gl` Map instance lives in a
 * `useEffect` so re-renders don't recreate the GL context.
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
import { useTheme } from "@/src/theme";

const VANCOUVER_CENTER: [number, number] = [-123.12, 49.28];
const DEFAULT_ZOOM = 11;
const SOURCE_ID = "rentwise-listings";
const CLUSTER_LAYER = "rentwise-clusters";
const CLUSTER_COUNT_LAYER = "rentwise-cluster-count";
const POINT_LAYER = "rentwise-points";

interface Props {
  listings: NormalizedListing[];
  onSelectListing: (id: string) => void;
  /** Fired when the user clicks "Search this area"; the bbox encodes
   * the visible viewport for the caller to re-run /search with. */
  onSearchBbox: (bbox: Bbox) => void;
}

export function MapView({ listings, onSelectListing, onSearchBbox }: Props) {
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

  return (
    <MapViewWeb
      listings={listings}
      onSelectListing={onSelectListing}
      onSearchBbox={onSearchBbox}
    />
  );
}

function MapViewWeb({ listings, onSelectListing, onSearchBbox }: Props) {
  const t = useTheme();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  // Keep the latest listing-id index in a ref so the click handler we
  // attach to the map (once) always sees fresh data.
  const idIndexRef = useRef<Map<string, NormalizedListing>>(new Map());
  const [moved, setMoved] = useState(false);
  const initialBboxRef = useRef<Bbox | null>(null);

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
      map.addSource(SOURCE_ID, {
        type: "geojson",
        data: featureCollection([]),
        cluster: true,
        clusterRadius: 60,
        clusterMaxZoom: 14,
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
          "circle-color": "#1d4ed8",
          "circle-radius": 8,
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
});
