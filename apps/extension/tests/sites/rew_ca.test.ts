import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

import { SeenCache } from "@/content/base";
import {
  classifyPage,
  extractFromDetail,
  extractFromSearchResults,
  parseListingId,
  runExtraction,
  SCHEMA_VERSION,
  SOURCE,
} from "@/content/sites/rew_ca";

function loadFixture(name: string): Document {
  const path = resolve(__dirname, "..", "fixtures", "rew_ca", name);
  return new JSDOM(readFileSync(path, "utf8")).window.document;
}

describe("rew_ca classifyPage", () => {
  it.each([
    ["/properties/areas/vancouver-bc", "search_results"],
    ["/properties/r-111-foo", "listing_detail"],
    ["/properties/areas", null], // missing trailing area name
    ["/about", null],
  ])("classifies %s", (path, expected) => {
    expect(classifyPage(path)).toBe(expected);
  });
});

describe("rew_ca parseListingId", () => {
  it("returns null for the area-search path", () => {
    expect(parseListingId("https://www.rew.ca/properties/areas/vancouver-bc")).toBeNull();
  });
  it("returns the slug for a property URL", () => {
    expect(parseListingId("https://www.rew.ca/properties/r-111-foo")).toBe("r-111-foo");
  });
});

describe("rew_ca extractFromSearchResults", () => {
  const doc = loadFixture("search_results.html");
  const items = extractFromSearchResults(doc, "https://www.rew.ca/properties/areas/vancouver-bc");
  it("captures every card", () => expect(items).toHaveLength(2));
  it("parses price and beds", () => {
    expect(items[0]?.source_listing_id).toBe("r-111-foo");
    expect(items[0]?.price).toBe(2950);
    expect(items[0]?.bedrooms).toBe(1);
    expect(items[1]?.bedrooms).toBe(3);
  });
});

describe("rew_ca extractFromDetail", () => {
  const doc = loadFixture("listing_detail.html");
  const item = extractFromDetail(doc, "https://www.rew.ca/properties/r-111-foo");
  it("populates fields", () => {
    expect(item?.bedrooms).toBe(1);
    expect(item?.bathrooms).toBe(1);
    expect(item?.sqft).toBe(680);
    expect(item?.neighborhood).toBe("Yaletown");
  });
  it("snippet is ≤200 chars", () => {
    expect((item?.description_snippet ?? "").length).toBeLessThanOrEqual(200);
  });
});

describe("rew_ca runExtraction", () => {
  it("captures search results", () => {
    const doc = loadFixture("search_results.html");
    const out = runExtraction(
      doc,
      "https://www.rew.ca/properties/areas/vancouver-bc",
      new SeenCache(),
    );
    expect(out.kind).toBe("captured");
    if (out.kind !== "captured") throw new Error("unreachable");
    expect(out.payload.source).toBe(SOURCE);
    expect(out.payload.schema_version).toBe(SCHEMA_VERSION);
  });
});
