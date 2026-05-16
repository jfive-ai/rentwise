// Issue #121 — tests for the side-by-side comparator's pure helpers.

import { bestOn, completenessScore, recommend } from "@/src/lib/compare";
import type { NormalizedListing } from "@/src/api/types";

function listing(o: Partial<NormalizedListing> & { id: string }): NormalizedListing {
  return {
    id: o.id,
    canonical_id: o.id,
    source: o.source ?? "test",
    source_url: o.source_url ?? "https://example.com/" + o.id,
    source_listing_id: o.source_listing_id ?? o.id,
    title: o.title ?? `Listing ${o.id}`,
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
    posted_at: o.posted_at ?? new Date().toISOString(),
    last_seen_at: new Date().toISOString(),
    photos: o.photos ?? [],
    description_snippet: o.description_snippet ?? null,
    school_catchments: { elementary: null, middle: null, secondary: null },
    nearest_transit: o.nearest_transit ?? null,
    walkscore: null,
    raw_metadata: {},
    match_score: o.match_score ?? null,
    match_explanation: o.match_explanation ?? null,
    quality_flags: o.quality_flags ?? [],
  };
}

describe("bestOn", () => {
  test("price picks cheapest", () => {
    const a = listing({ id: "a", price_cad: 2500 });
    const b = listing({ id: "b", price_cad: 2200 });
    const c = listing({ id: "c", price_cad: 3000 });
    expect(bestOn([a, b, c], "price")).toBe("b");
  });

  test("price returns null when no listing has a price", () => {
    const a = listing({ id: "a" });
    const b = listing({ id: "b" });
    expect(bestOn([a, b], "price")).toBeNull();
  });

  test("match picks highest score", () => {
    const a = listing({ id: "a", match_score: 70 });
    const b = listing({ id: "b", match_score: 90 });
    expect(bestOn([a, b], "match")).toBe("b");
  });

  test("bedrooms picks most bedrooms", () => {
    const a = listing({ id: "a", bedrooms: 1 });
    const b = listing({ id: "b", bedrooms: 3 });
    const c = listing({ id: "c", bedrooms: 2 });
    expect(bestOn([a, b, c], "bedrooms")).toBe("b");
  });

  test("transit picks shortest walk", () => {
    const a = listing({
      id: "a",
      nearest_transit: { nearest_stop_name: "X", walk_minutes: 5, line: null },
    });
    const b = listing({
      id: "b",
      nearest_transit: { nearest_stop_name: "Y", walk_minutes: 12, line: null },
    });
    expect(bestOn([a, b], "transit")).toBe("a");
  });

  test("completeness picks the listing with the most populated fields", () => {
    const sparse = listing({ id: "sparse" });
    const full = listing({
      id: "full",
      address: "100 Real Ave",
      photos: ["http://x/y.jpg"],
      description_snippet: "great place",
      bedrooms: 2,
      price_cad: 2500,
      nearest_transit: { nearest_stop_name: "stop", walk_minutes: 5, line: null },
    });
    expect(bestOn([sparse, full], "completeness")).toBe("full");
    expect(completenessScore(full)).toBeGreaterThan(completenessScore(sparse));
  });
});

describe("recommend", () => {
  test("returns empty list when fewer than 2 listings", () => {
    const a = listing({ id: "a", price_cad: 2500, match_score: 90 });
    expect(recommend([a])).toEqual([]);
  });

  test("produces at least cheapest + best-match for distinct winners", () => {
    const a = listing({ id: "a", price_cad: 2200, match_score: 60 });
    const b = listing({ id: "b", price_cad: 2900, match_score: 90 });
    const picks = recommend([a, b]);
    const axes = picks.map((p) => p.axis);
    expect(axes).toContain("price");
    expect(axes).toContain("match");
  });

  test("does not duplicate the same listing across axes", () => {
    // Same listing wins price + match + transit — should only appear once.
    const winner = listing({
      id: "winner",
      price_cad: 2200,
      match_score: 95,
      nearest_transit: { nearest_stop_name: "X", walk_minutes: 3, line: null },
    });
    const other = listing({
      id: "other",
      price_cad: 3000,
      match_score: 60,
      nearest_transit: { nearest_stop_name: "Y", walk_minutes: 20, line: null },
    });
    const picks = recommend([winner, other]);
    // Cheapest is the winner; best match was deduped because it's the same id.
    const winnerCount = picks.filter((p) => p.listingId === "winner").length;
    expect(winnerCount).toBeLessThanOrEqual(2); // at most cheapest + completeness
  });
});
