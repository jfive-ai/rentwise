import { groupByCanonical } from "@/src/lib/listingClusters";
import type { NormalizedListing } from "@/src/api/types";

const ZERO_UUID = "00000000-0000-0000-0000-000000000000";

function makeListing(
  id: string,
  canonical_id: string,
  overrides: Partial<NormalizedListing> = {},
): NormalizedListing {
  return {
    id,
    canonical_id,
    source: "craigslist",
    source_url: "https://example.com",
    source_listing_id: id,
    title: `Listing ${id}`,
    address: null,
    address_normalized: null,
    lat: null,
    lon: null,
    bedrooms: null,
    bathrooms: null,
    price_cad: null,
    pets_allowed: null,
    furnished: null,
    available_date: null,
    posted_at: "2026-01-01T00:00:00Z",
    last_seen_at: "2026-01-01T00:00:00Z",
    photos: [],
    description_snippet: null,
    school_catchments: { elementary: null, middle: null, secondary: null },
    nearest_transit: null,
    walkscore: null,
    raw_metadata: {},
    ...overrides,
  };
}

describe("groupByCanonical", () => {
  it("returns [] for an empty input", () => {
    expect(groupByCanonical([])).toEqual([]);
  });

  it("returns one cluster per listing when canonical_ids are unique", () => {
    const a = makeListing("1", "c1");
    const b = makeListing("2", "c2");
    const out = groupByCanonical([a, b]);
    expect(out).toHaveLength(2);
    expect(out[0]!.alternates).toEqual([]);
    expect(out[1]!.alternates).toEqual([]);
  });

  it("collapses listings sharing a canonical_id", () => {
    const a = makeListing("1", "shared");
    const b = makeListing("2", "shared", { source: "rentals_ca" });
    const out = groupByCanonical([a, b]);
    expect(out).toHaveLength(1);
    const [{ primary, alternates }] = out;
    expect([primary.id, ...alternates.map((x) => x.id)].sort()).toEqual(["1", "2"]);
  });

  it("preserves input order across cluster boundaries", () => {
    const a = makeListing("a", "c1");
    const b = makeListing("b", "c2");
    const a2 = makeListing("a2", "c1");
    const c = makeListing("c", "c3");
    const out = groupByCanonical([a, b, a2, c]);
    // c1 group's first occurrence is at index 0, then c2 (1), then c3 (3).
    expect(out.map((x) => x.primary.canonical_id)).toEqual(["c1", "c2", "c3"]);
  });

  it("picks the field-richest listing as primary", () => {
    const sparse = makeListing("sparse", "shared");
    const rich = makeListing("rich", "shared", {
      address: "1234 W 4th Ave",
      address_normalized: "1234 west 4th avenue",
      lat: 49.27,
      lon: -123.15,
      price_cad: 2800,
      bedrooms: 2,
      bathrooms: 1,
      description_snippet: "south facing",
      photos: ["https://example.com/p.jpg"],
      school_catchments: { elementary: null, middle: null, secondary: "Lord Byng" },
      nearest_transit: { nearest_stop_name: "Broadway", walk_minutes: 5, line: "Canada Line" },
    });
    // Insert sparse first to confirm primary selection beats input order.
    const out = groupByCanonical([sparse, rich]);
    expect(out).toHaveLength(1);
    expect(out[0]!.primary.id).toBe("rich");
    expect(out[0]!.alternates.map((x) => x.id)).toEqual(["sparse"]);
  });

  it("handles a real-world UUID canonical_id without crashing", () => {
    const a = makeListing("a", ZERO_UUID);
    expect(() => groupByCanonical([a])).not.toThrow();
  });
});
