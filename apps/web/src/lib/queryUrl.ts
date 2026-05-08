/**
 * Phase 7 PR-C-2: serialize/deserialize a NormalizedQuery to URL search
 * params so a search is shareable and bookmarkable.
 *
 * Rules:
 * - Skip default / empty values so URLs stay short ("?" if everything is empty).
 * - Numbers as plain strings; arrays as comma-separated.
 * - Pets/furnished only emitted when non-"any".
 * - Decode is forgiving: unknown keys are ignored, malformed numbers fall
 *   through to the default. The point is shareable URLs, not validation —
 *   the backend re-validates the query on POST /search.
 */

import {
  emptyQuery,
  type FurnishedPolicy,
  type NormalizedQuery,
  type PetPolicy,
} from "@/src/api/types";

const PET_VALUES: readonly PetPolicy[] = ["required", "ok", "no", "any"];
const FURNISHED_VALUES: readonly FurnishedPolicy[] = ["yes", "no", "any"];

function setIfPresent(p: URLSearchParams, key: string, value: string | null | undefined): void {
  if (value === null || value === undefined || value === "") return;
  p.set(key, value);
}

export function encodeQueryToParams(q: NormalizedQuery): URLSearchParams {
  const p = new URLSearchParams();
  if (q.bedrooms_min != null) p.set("bedrooms_min", String(q.bedrooms_min));
  if (q.bedrooms_max != null) p.set("bedrooms_max", String(q.bedrooms_max));
  if (q.price_min != null) p.set("price_min", String(q.price_min));
  if (q.price_max != null) p.set("price_max", String(q.price_max));
  if (q.neighborhoods.length > 0) p.set("neighborhoods", q.neighborhoods.join(","));
  setIfPresent(p, "school_catchment", q.school_catchment ?? null);
  if (q.pets !== "any") p.set("pets", q.pets);
  if (q.furnished !== "any") p.set("furnished", q.furnished);
  setIfPresent(p, "available_after", q.available_after ?? null);
  if (q.transit_max_walk_minutes != null)
    p.set("transit_max_walk_minutes", String(q.transit_max_walk_minutes));
  if (q.free_text_keywords.length > 0)
    p.set("free_text_keywords", q.free_text_keywords.join(","));
  return p;
}

/** Convenience for callers that just want the query string body. */
export function encodeQueryToString(q: NormalizedQuery): string {
  return encodeQueryToParams(q).toString();
}

function intOrNull(s: string | null): number | null {
  if (s == null || s === "") return null;
  const n = Number.parseInt(s, 10);
  return Number.isFinite(n) ? n : null;
}

function splitCsv(s: string | null): string[] {
  if (!s) return [];
  return s.split(",").map((x) => x.trim()).filter(Boolean);
}

export function decodeQueryFromParams(
  source: URLSearchParams | Record<string, string | string[] | undefined>,
): NormalizedQuery {
  // Normalize to URLSearchParams so we have one accessor shape.
  const p =
    source instanceof URLSearchParams
      ? source
      : new URLSearchParams(
          Object.entries(source).flatMap(([k, v]) =>
            v == null
              ? []
              : Array.isArray(v)
                ? [[k, v.join(",")] as [string, string]]
                : [[k, v] as [string, string]],
          ),
        );

  const base = emptyQuery();

  const bedroomsMin = intOrNull(p.get("bedrooms_min"));
  const bedroomsMax = intOrNull(p.get("bedrooms_max"));
  const priceMin = intOrNull(p.get("price_min"));
  const priceMax = intOrNull(p.get("price_max"));
  const transit = intOrNull(p.get("transit_max_walk_minutes"));

  const petsRaw = p.get("pets");
  const pets: PetPolicy = (PET_VALUES as readonly string[]).includes(petsRaw ?? "")
    ? (petsRaw as PetPolicy)
    : "any";
  const furnishedRaw = p.get("furnished");
  const furnished: FurnishedPolicy = (FURNISHED_VALUES as readonly string[]).includes(
    furnishedRaw ?? "",
  )
    ? (furnishedRaw as FurnishedPolicy)
    : "any";

  // Build atop emptyQuery() and only set optional fields when they parsed
  // to a non-null value. This keeps `decode(encode(empty)) === empty` (deep
  // equality) instead of forcing a bunch of explicit `null`s on every key.
  const out: NormalizedQuery = {
    ...base,
    neighborhoods: splitCsv(p.get("neighborhoods")),
    pets,
    furnished,
    free_text_keywords: splitCsv(p.get("free_text_keywords")),
  };
  if (bedroomsMin != null) out.bedrooms_min = bedroomsMin;
  if (bedroomsMax != null) out.bedrooms_max = bedroomsMax;
  if (priceMin != null) out.price_min = priceMin;
  if (priceMax != null) out.price_max = priceMax;
  const catchment = p.get("school_catchment");
  if (catchment) out.school_catchment = catchment;
  const after = p.get("available_after");
  if (after) out.available_after = after;
  if (transit != null) out.transit_max_walk_minutes = transit;
  return out;
}

/** True when the encoded URL form is non-empty. Used to decide auto-search on mount. */
export function hasAnyParams(q: NormalizedQuery): boolean {
  return encodeQueryToParams(q).toString().length > 0;
}
