// Issue #122 — derive a NormalizedQuery from a seed listing so the user
// can ask "show me more like this" with one click.
//
// Pure function over a NormalizedListing. Fields that are missing on
// the seed get skipped, never guessed. The price band is ±15% to give
// the user a usable result set without an exact-price match.

import type { NormalizedListing, NormalizedQuery } from "@/src/api/types";

const PRICE_BAND_PCT = 0.15;

export function findSimilar(listing: NormalizedListing): NormalizedQuery {
  const q: NormalizedQuery = {
    neighborhoods: [],
    pets: "any",
    furnished: "any",
    free_text_keywords: [],
  };

  if (listing.bedrooms != null) {
    q.bedrooms_min = listing.bedrooms;
    q.bedrooms_max = listing.bedrooms;
  }

  if (listing.price_cad != null) {
    q.price_min = Math.floor(listing.price_cad * (1 - PRICE_BAND_PCT));
    q.price_max = Math.ceil(listing.price_cad * (1 + PRICE_BAND_PCT));
  }

  if (listing.neighborhood) {
    q.neighborhoods = [listing.neighborhood];
  }

  return q;
}
