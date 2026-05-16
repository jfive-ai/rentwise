// Issue #121 — pure helpers powering the side-by-side comparator.
//
// Frontend-only feature: the API already returns everything we need
// (price, bedrooms, transit walk minutes, match score, quality flags).
// These helpers operate over a fixed array of listings and surface
// "best on X" picks plus a short textual recommendation. Deterministic
// — no LLM call required.

import type { NormalizedListing } from "@/src/api/types";

export type ComparisonAxis =
  | "price"
  | "bedrooms"
  | "transit"
  | "match"
  | "completeness";

export interface BestPick {
  axis: ComparisonAxis;
  listingId: string;
  /** Short prose describing why this listing wins on this axis. */
  reason: string;
}

/** Number of non-null fields present — proxy for "how complete is this listing". */
export function completenessScore(l: NormalizedListing): number {
  let n = 0;
  if (l.address) n++;
  if (l.photos && l.photos.length > 0) n++;
  if (l.description_snippet) n++;
  if (l.nearest_transit) n++;
  if (l.bedrooms != null) n++;
  if (l.price_cad != null) n++;
  return n;
}

/**
 * Return the id of the listing that wins on `axis`, or `null` when no
 * row has the data to compete (e.g. nobody has a transit walk time).
 */
export function bestOn(
  listings: NormalizedListing[],
  axis: ComparisonAxis,
): string | null {
  if (listings.length === 0) return null;

  if (axis === "price") {
    const priced = listings.filter((l) => l.price_cad != null);
    if (priced.length === 0) return null;
    return priced.reduce((a, b) =>
      (a.price_cad as number) <= (b.price_cad as number) ? a : b,
    ).id;
  }
  if (axis === "bedrooms") {
    const beds = listings.filter((l) => l.bedrooms != null);
    if (beds.length === 0) return null;
    // "Best on bedrooms" = most bedrooms.
    return beds.reduce((a, b) =>
      (a.bedrooms as number) >= (b.bedrooms as number) ? a : b,
    ).id;
  }
  if (axis === "transit") {
    const t = listings.filter((l) => l.nearest_transit != null);
    if (t.length === 0) return null;
    return t.reduce((a, b) =>
      (a.nearest_transit?.walk_minutes ?? Infinity) <=
      (b.nearest_transit?.walk_minutes ?? Infinity)
        ? a
        : b,
    ).id;
  }
  if (axis === "match") {
    const scored = listings.filter((l) => l.match_score != null);
    if (scored.length === 0) return null;
    return scored.reduce((a, b) =>
      (a.match_score as number) >= (b.match_score as number) ? a : b,
    ).id;
  }
  if (axis === "completeness") {
    return listings.reduce((a, b) =>
      completenessScore(a) >= completenessScore(b) ? a : b,
    ).id;
  }
  return null;
}

function shortTitle(l: NormalizedListing, fallback = "this listing"): string {
  return l.title.length > 40 ? `${l.title.slice(0, 37)}…` : l.title || fallback;
}

/**
 * Build a list of `BestPick` rows for the comparison footer. Each row is
 * a deterministic one-liner ("Cheapest: <title> at $X"). Stable order so
 * the UI doesn't re-shuffle on every render.
 */
export function recommend(listings: NormalizedListing[]): BestPick[] {
  if (listings.length < 2) return [];
  const out: BestPick[] = [];
  const byId = new Map(listings.map((l) => [l.id, l]));
  const cheapest = bestOn(listings, "price");
  if (cheapest) {
    const l = byId.get(cheapest)!;
    out.push({
      axis: "price",
      listingId: cheapest,
      reason: `Cheapest: ${shortTitle(l)} at $${l.price_cad?.toLocaleString("en-CA")}/mo`,
    });
  }
  const bestMatch = bestOn(listings, "match");
  if (bestMatch && bestMatch !== cheapest) {
    const l = byId.get(bestMatch)!;
    out.push({
      axis: "match",
      listingId: bestMatch,
      reason: `Best overall match: ${shortTitle(l)} (score ${l.match_score})`,
    });
  }
  const closest = bestOn(listings, "transit");
  // Codex P2 on PR #129: dedup against ALL prior picks, not just the
  // best-match pick. The same listing was emitting twice when it was
  // both cheapest and closest-to-transit (and best-match was someone
  // else), wasting a recommendation slot.
  if (closest && !out.some((p) => p.listingId === closest)) {
    const l = byId.get(closest)!;
    out.push({
      axis: "transit",
      listingId: closest,
      reason: `Closest to transit: ${shortTitle(l)} (${l.nearest_transit?.walk_minutes} min walk)`,
    });
  }
  const fullest = bestOn(listings, "completeness");
  if (fullest && !out.some((p) => p.listingId === fullest)) {
    const l = byId.get(fullest)!;
    out.push({
      axis: "completeness",
      listingId: fullest,
      reason: `Most complete listing: ${shortTitle(l)}`,
    });
  }
  return out;
}
