/**
 * Pure helpers for the Phase 7 map view.
 *
 * Live `maplibre-gl` / `supercluster` instances stay inside
 * `MapView.tsx`; everything that's testable without a WebGL context
 * lives here so we can exercise it under jest+jsdom.
 */

import type { Feature, FeatureCollection, Point } from "geojson";
import type { NormalizedListing } from "@/src/api/types";

export type ListingProperties = {
  /** The listing's `id` — keeps the cluster source keyed and the click
   * handler O(1) when leafing back to the listing object. */
  id: string;
  source: string;
  title: string;
  /** Stringified for compactness on the wire; consumers parse on demand. */
  price: number | null;
  bedrooms: number | null;
};

export type ListingFeature = Feature<Point, ListingProperties>;

/** Bbox in MapLibre's [west, south, east, north] order. */
export type Bbox = [number, number, number, number];

/**
 * Build a GeoJSON FeatureCollection from listings, dropping any
 * without a usable `(lat, lon)`. The dropped count is what
 * `SearchScreen` shows in its "N off-map listings" footer.
 */
export function listingsToFeatures(listings: NormalizedListing[]): {
  features: ListingFeature[];
  dropped: number;
} {
  const features: ListingFeature[] = [];
  let dropped = 0;
  for (const l of listings) {
    if (l.lat == null || l.lon == null || !Number.isFinite(l.lat) || !Number.isFinite(l.lon)) {
      dropped += 1;
      continue;
    }
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [l.lon, l.lat] },
      properties: {
        id: l.id,
        source: l.source,
        title: l.title,
        price: l.price_cad,
        bedrooms: l.bedrooms,
      },
    });
  }
  return { features, dropped };
}

export function featureCollection(features: ListingFeature[]): FeatureCollection<Point, ListingProperties> {
  return { type: "FeatureCollection", features };
}

/**
 * Round-trip a bbox through a comma-separated URL param. The shape is
 * deliberately compact: callers use `bbox=west,south,east,north`.
 */
export function bboxToParam(bbox: Bbox): string {
  return bbox.map((n) => round(n, 5)).join(",");
}

export function parseBboxParam(raw: string | null | undefined): Bbox | null {
  if (!raw) return null;
  const parts = raw.split(",");
  if (parts.length !== 4) return null;
  const nums = parts.map((p) => Number.parseFloat(p));
  if (nums.some((n) => !Number.isFinite(n))) return null;
  const [w, s, e, n] = nums as [number, number, number, number];
  if (w >= e || s >= n) return null; // degenerate
  if (w < -180 || e > 180 || s < -90 || n > 90) return null;
  return [w, s, e, n];
}

/** True if `b` is meaningfully different from `a` (≥ ~50 m at the equator). */
export function bboxesDiffer(a: Bbox, b: Bbox, epsilonDegrees = 0.0005): boolean {
  for (let i = 0; i < 4; i++) {
    if (Math.abs(a[i]! - b[i]!) > epsilonDegrees) return true;
  }
  return false;
}

function round(n: number, decimals: number): number {
  const factor = 10 ** decimals;
  return Math.round(n * factor) / factor;
}
