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
} from "@/content/sites/zumper";

function loadFixture(name: string): Document {
  const path = resolve(__dirname, "..", "fixtures", "zumper", name);
  return new JSDOM(readFileSync(path, "utf8")).window.document;
}

describe("zumper classifyPage", () => {
  it.each([
    ["/apartments-for-rent/vancouver-bc", "search_results"],
    ["/apartment/z111/foo", "listing_detail"],
    ["/building/b222/foo", "listing_detail"],
    ["/listings/x333/foo", "listing_detail"],
    ["/about", null],
  ])("classifies %s", (path, expected) => {
    expect(classifyPage(path)).toBe(expected);
  });
});

describe("zumper parseListingId", () => {
  it("apartment", () => {
    expect(parseListingId("https://www.zumper.com/apartment/z111/foo")).toBe("z111");
  });
  it("building", () => {
    expect(parseListingId("https://www.zumper.com/building/b222/foo")).toBe("b222");
  });
});

describe("zumper extractFromSearchResults", () => {
  const doc = loadFixture("search_results.html");
  const baseUrl = "https://www.zumper.com/apartments-for-rent/vancouver-bc";
  const items = extractFromSearchResults(doc, baseUrl);

  it("captures every card", () => expect(items).toHaveLength(2));
  it("parses ids + prices + beds", () => {
    expect(items[0]?.source_listing_id).toBe("z111");
    expect(items[0]?.price).toBe(2650);
    expect(items[0]?.bedrooms).toBe(1);
    expect(items[1]?.source_listing_id).toBe("b222");
    expect(items[1]?.price).toBe(3800);
  });
});

describe("zumper extractFromDetail", () => {
  const doc = loadFixture("listing_detail.html");
  const item = extractFromDetail(doc, "https://www.zumper.com/apartment/z111/foo");
  it("populates fields", () => {
    expect(item?.bedrooms).toBe(1);
    expect(item?.bathrooms).toBe(1);
    expect(item?.sqft).toBe(540);
    expect(item?.neighborhood).toBe("Mount Pleasant");
  });
  it("snippet is ≤200 chars", () => {
    expect((item?.description_snippet ?? "").length).toBeLessThanOrEqual(200);
  });
});

describe("zumper runExtraction", () => {
  it("captures search results", () => {
    const doc = loadFixture("search_results.html");
    const out = runExtraction(
      doc,
      "https://www.zumper.com/apartments-for-rent/vancouver-bc",
      new SeenCache(),
      new Date("2026-05-07T12:00:00Z"),
    );
    expect(out.kind).toBe("captured");
    if (out.kind !== "captured") throw new Error("unreachable");
    expect(out.payload.source).toBe(SOURCE);
    expect(out.payload.schema_version).toBe(SCHEMA_VERSION);
  });

  it("emits degraded when search container missing", () => {
    const doc = new JSDOM("<!doctype html><html><body></body></html>").window.document;
    const out = runExtraction(
      doc,
      "https://www.zumper.com/apartments-for-rent/vancouver-bc",
      new SeenCache(),
    );
    expect(out.kind).toBe("degraded");
  });
});
