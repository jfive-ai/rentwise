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
} from "@/content/sites/liv_rent";

function loadFixture(name: string): Document {
  const path = resolve(__dirname, "..", "fixtures", "liv_rent", name);
  return new JSDOM(readFileSync(path, "utf8")).window.document;
}

describe("liv_rent classifyPage", () => {
  it.each([
    ["/listings/vancouver", "search_results"],
    ["/listings/burnaby", "search_results"],
    ["/listings/lr-111-fairview", "listing_detail"],
    ["/about", null],
  ])("classifies %s", (path, expected) => {
    expect(classifyPage(path)).toBe(expected);
  });
});

describe("liv_rent parseListingId", () => {
  it("returns null for the search city slug", () => {
    expect(parseListingId("https://liv.rent/listings/vancouver")).toBeNull();
  });
  it("returns the listing slug otherwise", () => {
    expect(parseListingId("https://liv.rent/listings/lr-111-fairview")).toBe("lr-111-fairview");
  });
});

describe("liv_rent extractFromSearchResults", () => {
  const doc = loadFixture("search_results.html");
  const items = extractFromSearchResults(doc, "https://liv.rent/listings/vancouver");
  it("captures every card", () => expect(items).toHaveLength(2));
  it("studio → 0 beds", () => {
    expect(items[1]?.bedrooms).toBe(0);
  });
});

describe("liv_rent extractFromDetail", () => {
  const doc = loadFixture("listing_detail.html");
  const item = extractFromDetail(doc, "https://liv.rent/listings/lr-111-fairview");
  it("populates fields", () => {
    expect(item?.bedrooms).toBe(1);
    expect(item?.bathrooms).toBe(1);
    expect(item?.sqft).toBe(560);
    expect(item?.neighborhood).toBe("Fairview");
  });
});

describe("liv_rent runExtraction", () => {
  it("captures search results", () => {
    const doc = loadFixture("search_results.html");
    const out = runExtraction(doc, "https://liv.rent/listings/vancouver", new SeenCache());
    expect(out.kind).toBe("captured");
    if (out.kind !== "captured") throw new Error("unreachable");
    expect(out.payload.source).toBe(SOURCE);
    expect(out.payload.schema_version).toBe(SCHEMA_VERSION);
  });
});
