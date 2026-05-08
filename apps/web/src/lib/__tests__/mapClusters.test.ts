import {
  bboxToParam,
  bboxesDiffer,
  listingsToFeatures,
  parseBboxParam,
} from "@/src/lib/mapClusters";
import type { NormalizedListing } from "@/src/api/types";

function makeListing(
  id: string,
  overrides: Partial<NormalizedListing> = {},
): NormalizedListing {
  return {
    id,
    canonical_id: id,
    source: "craigslist",
    source_url: "https://example.com",
    source_listing_id: id,
    title: `Listing ${id}`,
    address: null,
    address_normalized: null,
    lat: 49.27,
    lon: -123.13,
    bedrooms: 2,
    bathrooms: null,
    price_cad: 2800,
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

describe("listingsToFeatures", () => {
  it("returns one feature per listing with valid coords", () => {
    const out = listingsToFeatures([
      makeListing("a"),
      makeListing("b", { lat: 49.28, lon: -123.12 }),
    ]);
    expect(out.dropped).toBe(0);
    expect(out.features).toHaveLength(2);
    expect(out.features[0]!.geometry.coordinates).toEqual([-123.13, 49.27]);
    expect(out.features[0]!.properties.id).toBe("a");
  });

  it("drops listings missing lat or lon", () => {
    const out = listingsToFeatures([
      makeListing("ok"),
      makeListing("no-lat", { lat: null }),
      makeListing("no-lon", { lon: null }),
      makeListing("both-null", { lat: null, lon: null }),
    ]);
    expect(out.features).toHaveLength(1);
    expect(out.dropped).toBe(3);
  });

  it("drops listings with non-finite coordinates", () => {
    const out = listingsToFeatures([
      makeListing("nan", { lat: Number.NaN, lon: -123 }),
      makeListing("inf", { lat: Number.POSITIVE_INFINITY, lon: -123 }),
    ]);
    expect(out.features).toHaveLength(0);
    expect(out.dropped).toBe(2);
  });

  it("preserves listing fields needed for the popup / hover", () => {
    const out = listingsToFeatures([
      makeListing("a", { title: "Sunny", price_cad: 1500, bedrooms: 1 }),
    ]);
    const props = out.features[0]!.properties;
    expect(props.title).toBe("Sunny");
    expect(props.price).toBe(1500);
    expect(props.bedrooms).toBe(1);
  });
});

describe("bbox URL round-trip", () => {
  it("encodes to comma-separated, 5 decimal places", () => {
    expect(bboxToParam([-123.1234567, 49.2, -123.0, 49.3])).toBe(
      "-123.12346,49.2,-123,49.3",
    );
  });

  it("decodes a well-formed bbox param", () => {
    expect(parseBboxParam("-123.2,49.2,-123.0,49.3")).toEqual([
      -123.2, 49.2, -123, 49.3,
    ]);
  });

  it("rejects mis-formatted input", () => {
    expect(parseBboxParam(null)).toBeNull();
    expect(parseBboxParam("")).toBeNull();
    expect(parseBboxParam("1,2,3")).toBeNull();
    expect(parseBboxParam("a,b,c,d")).toBeNull();
  });

  it("rejects degenerate / out-of-range bboxes", () => {
    expect(parseBboxParam("0,0,0,0")).toBeNull(); // zero area
    expect(parseBboxParam("-200,49,180,50")).toBeNull(); // west out of range
    expect(parseBboxParam("-123,90.5,-122,91")).toBeNull(); // south out of range
  });
});

describe("bboxesDiffer", () => {
  it("returns false when all four sides are within epsilon", () => {
    expect(
      bboxesDiffer(
        [-123.1, 49.2, -123.0, 49.3],
        [-123.1, 49.2, -123.0, 49.3],
      ),
    ).toBe(false);
  });

  it("returns true when at least one side is outside epsilon", () => {
    expect(
      bboxesDiffer(
        [-123.1, 49.2, -123.0, 49.3],
        [-123.1, 49.2, -123.0, 49.31],
      ),
    ).toBe(true);
  });
});
