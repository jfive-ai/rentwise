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
} from "@/content/sites/padmapper";

function loadFixture(name: string): Document {
  const path = resolve(__dirname, "..", "fixtures", "padmapper", name);
  return new JSDOM(readFileSync(path, "utf8")).window.document;
}

describe("padmapper classifyPage", () => {
  it.each([
    ["/apartments/vancouver-bc", "search_results"],
    ["/apartments/vancouver-bc/something", "search_results"],
    ["/buildings/p123/the-quarry", "listing_detail"],
    ["/rentals/r987/foo", "listing_detail"],
    ["/about", null],
    ["/", null],
  ])("classifies %s", (path, expected) => {
    expect(classifyPage(path)).toBe(expected);
  });
});

describe("padmapper parseListingId", () => {
  it("works for /buildings/<id>/...", () => {
    expect(parseListingId("https://www.padmapper.com/buildings/p123456/the-quarry")).toBe("p123456");
  });
  it("works for /rentals/<id>/...", () => {
    expect(parseListingId("https://www.padmapper.com/rentals/r987/cambie-loft")).toBe("r987");
  });
  it("returns null otherwise", () => {
    expect(parseListingId("https://www.padmapper.com/apartments/vancouver-bc")).toBeNull();
  });
});

describe("padmapper extractFromSearchResults", () => {
  const doc = loadFixture("search_results.html");
  const baseUrl = "https://www.padmapper.com/apartments/vancouver-bc";
  const items = extractFromSearchResults(doc, baseUrl);

  it("captures every visible card", () => {
    expect(items).toHaveLength(2);
  });

  it("resolves relative hrefs and pulls listing ids", () => {
    expect(items[0]?.url).toBe("https://www.padmapper.com/buildings/p123456/the-quarry");
    expect(items[0]?.source_listing_id).toBe("p123456");
    expect(items[1]?.source_listing_id).toBe("r987");
  });

  it("parses price and bedrooms", () => {
    expect(items[0]?.price).toBe(2400);
    expect(items[0]?.bedrooms).toBe(1);
    expect(items[1]?.bedrooms).toBe(2);
  });
});

describe("padmapper extractFromDetail", () => {
  const doc = loadFixture("listing_detail.html");
  const baseUrl = "https://www.padmapper.com/buildings/p123456/the-quarry";
  const item = extractFromDetail(doc, baseUrl);

  it("returns a populated detail listing", () => {
    expect(item?.source_listing_id).toBe("p123456");
    expect(item?.bedrooms).toBe(1);
    expect(item?.bathrooms).toBe(1);
    expect(item?.sqft).toBe(650);
    expect(item?.neighborhood).toBe("Strathcona");
  });

  it("captures snippet capped at 200 chars", () => {
    expect((item?.description_snippet ?? "").length).toBeLessThanOrEqual(200);
  });

  it("collects all photo URLs", () => {
    expect(item?.photo_urls).toHaveLength(2);
  });
});

describe("padmapper runExtraction", () => {
  it("captures from a search-results URL", () => {
    const doc = loadFixture("search_results.html");
    const out = runExtraction(
      doc,
      "https://www.padmapper.com/apartments/vancouver-bc",
      new SeenCache(),
      new Date("2026-05-07T12:00:00Z"),
    );
    expect(out.kind).toBe("captured");
    if (out.kind !== "captured") throw new Error("unreachable");
    expect(out.payload.source).toBe(SOURCE);
    expect(out.payload.schema_version).toBe(SCHEMA_VERSION);
  });

  it("idempotency — second run on same doc skips", () => {
    const doc = loadFixture("search_results.html");
    const seen = new SeenCache();
    runExtraction(doc, "https://www.padmapper.com/apartments/vancouver-bc", seen);
    const second = runExtraction(doc, "https://www.padmapper.com/apartments/vancouver-bc", seen);
    expect(second.kind).toBe("skipped");
  });

  it("emits degraded when search container is missing", () => {
    const doc = new JSDOM("<!doctype html><html><body></body></html>").window.document;
    const out = runExtraction(
      doc,
      "https://www.padmapper.com/apartments/vancouver-bc",
      new SeenCache(),
    );
    expect(out.kind).toBe("degraded");
  });
});
