// Issue #122 — tests for the derived "find similar" query.

import { findSimilar } from "@/src/lib/findSimilar";
import type { NormalizedListing } from "@/src/api/types";

function listing(o: Partial<NormalizedListing> & { id: string }): NormalizedListing {
  return {
    id: o.id,
    canonical_id: o.id,
    source: "test",
    source_url: "https://example.com/x",
    source_listing_id: o.id,
    title: "Listing",
    address: o.address ?? null,
    address_normalized: null,
    lat: null,
    lon: null,
    bedrooms: o.bedrooms ?? null,
    bathrooms: null,
    price_cad: o.price_cad ?? null,
    pets_allowed: null,
    furnished: null,
    available_date: null,
    posted_at: new Date().toISOString(),
    last_seen_at: new Date().toISOString(),
    photos: [],
    description_snippet: null,
    school_catchments: { elementary: null, middle: null, secondary: null },
    nearest_transit: null,
    walkscore: null,
    raw_metadata: {},
    neighborhood: (o as { neighborhood?: string | null }).neighborhood ?? null,
  } as NormalizedListing;
}

describe("findSimilar", () => {
  test("derives bedroom range from seed", () => {
    const seed = listing({ id: "s", bedrooms: 2 });
    const q = findSimilar(seed);
    expect(q.bedrooms_min).toBe(2);
    expect(q.bedrooms_max).toBe(2);
  });

  test("derives ±15% price band", () => {
    const seed = listing({ id: "s", price_cad: 2000 });
    const q = findSimilar(seed);
    expect(q.price_min).toBe(1700);
    expect(q.price_max).toBe(2300);
  });

  test("skips bedroom bound when missing", () => {
    const seed = listing({ id: "s" });
    const q = findSimilar(seed);
    expect(q.bedrooms_min).toBeUndefined();
    expect(q.bedrooms_max).toBeUndefined();
  });

  test("propagates neighborhood when known", () => {
    const seed = listing({ id: "s" });
    (seed as { neighborhood?: string }).neighborhood = "Kitsilano";
    const q = findSimilar(seed);
    expect(q.neighborhoods).toEqual(["Kitsilano"]);
  });

  test("returns valid query even when seed has no usable fields", () => {
    const q = findSimilar(listing({ id: "s" }));
    expect(q.neighborhoods).toEqual([]);
    expect(q.pets).toBe("any");
    expect(q.furnished).toBe("any");
    expect(q.free_text_keywords).toEqual([]);
  });
});
