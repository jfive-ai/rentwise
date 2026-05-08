/**
 * Group a flat list of listings by canonical_id (Phase 4 PR-C).
 *
 * Listings sharing a canonical_id describe the same property reached
 * via different sources. This helper picks a primary representative
 * and keeps the rest as alternates so the UI can collapse the cluster
 * into a single card with an "Also on …" expansion.
 *
 * Sort stability: each cluster's position in the output preserves the
 * primary's position in the input. The aggregator already applies the
 * sort order to the flat list, so the cluster ordering inherits it.
 */

import type { NormalizedListing } from "@/src/api/types";

export interface Cluster {
  primary: NormalizedListing;
  alternates: NormalizedListing[];
}

/** How many non-null fields a listing has, for primary selection. */
function fieldRichness(l: NormalizedListing): number {
  let n = 0;
  if (l.address) n += 1;
  if (l.address_normalized) n += 1;
  if (l.lat != null && l.lon != null) n += 1;
  if (l.price_cad != null) n += 1;
  if (l.bedrooms != null) n += 1;
  if (l.bathrooms != null) n += 1;
  if (l.description_snippet) n += 1;
  if (l.photos.length > 0) n += 1;
  if (l.school_catchments?.elementary || l.school_catchments?.secondary) n += 1;
  if (l.nearest_transit) n += 1;
  return n;
}

/** Pick the listing with the most populated fields. Ties → first one. */
function pickPrimary(listings: NormalizedListing[]): NormalizedListing {
  let best = listings[0]!;
  let bestScore = fieldRichness(best);
  for (const l of listings.slice(1)) {
    const s = fieldRichness(l);
    if (s > bestScore) {
      best = l;
      bestScore = s;
    }
  }
  return best;
}

export function groupByCanonical(listings: NormalizedListing[]): Cluster[] {
  if (listings.length === 0) return [];

  // First pass: group, preserving the input order of the first occurrence
  // of each canonical_id so the output cluster order matches input order.
  const order: string[] = [];
  const groups = new Map<string, NormalizedListing[]>();
  for (const l of listings) {
    const key = l.canonical_id;
    const existing = groups.get(key);
    if (existing) {
      existing.push(l);
    } else {
      groups.set(key, [l]);
      order.push(key);
    }
  }

  const out: Cluster[] = [];
  for (const key of order) {
    const members = groups.get(key)!;
    if (members.length === 1) {
      out.push({ primary: members[0]!, alternates: [] });
      continue;
    }
    const primary = pickPrimary(members);
    out.push({
      primary,
      alternates: members.filter((m) => m.id !== primary.id),
    });
  }
  return out;
}
