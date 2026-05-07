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
} from "@/content/sites/facebook_marketplace";

function loadFixture(name: string): Document {
  const path = resolve(__dirname, "..", "fixtures", "facebook_marketplace", name);
  return new JSDOM(readFileSync(path, "utf8")).window.document;
}

describe("facebook_marketplace classifyPage", () => {
  it.each([
    ["/marketplace/vancouver/propertyrentals", "search_results"],
    ["/marketplace/vancouver/propertyrentals?minPrice=1000", "search_results"],
    ["/marketplace/item/1234567890123456/", "listing_detail"],
    ["/marketplace/", null],
    ["/marketplace/vancouver/cars", null],
    ["/profile/me", null],
  ])("classifies %s", (pathQuery, expected) => {
    // Use just the pathname before any "?" — classifyPage takes pathname.
    const path = pathQuery.split("?")[0]!;
    expect(classifyPage(path)).toBe(expected);
  });
});

describe("facebook_marketplace parseListingId", () => {
  it("works on the canonical detail URL", () => {
    expect(parseListingId("https://www.facebook.com/marketplace/item/1234567890123456/")).toBe(
      "1234567890123456",
    );
  });
  it("returns null for non-item URLs", () => {
    expect(parseListingId("https://www.facebook.com/marketplace/vancouver/propertyrentals")).toBeNull();
  });
});

describe("facebook_marketplace extractFromSearchResults", () => {
  const doc = loadFixture("search_results.html");
  const items = extractFromSearchResults(
    doc,
    "https://www.facebook.com/marketplace/vancouver/propertyrentals",
  );
  it("captures every card", () => expect(items).toHaveLength(2));
  it("dedupes by listing id when multiple links point to the same item", () => {
    const dupDoc = new JSDOM(
      `<!doctype html><html><body><div role="main"><div role="feed">
        <div role="article"><a href="/marketplace/item/111/"><span>$1000</span><span>A</span></a></div>
        <div role="article"><a href="/marketplace/item/111/?ref=2"><span>$1000</span><span>A</span></a></div>
      </div></div></body></html>`,
    ).window.document;
    const out = extractFromSearchResults(dupDoc, "https://www.facebook.com/marketplace/vancouver/propertyrentals");
    expect(out).toHaveLength(1);
  });
  it("parses prices from search cards", () => {
    expect(items[0]?.price).toBe(2400);
    expect(items[1]?.price).toBe(1800);
  });
  it("captures the title (non-price span)", () => {
    expect(items[0]?.title).toContain("Mt Pleasant");
    expect(items[1]?.title).toContain("studio");
  });
});

describe("facebook_marketplace extractFromDetail", () => {
  const doc = loadFixture("listing_detail.html");
  const item = extractFromDetail(
    doc,
    "https://www.facebook.com/marketplace/item/1234567890123456/",
  );
  it("populates fields", () => {
    expect(item?.source_listing_id).toBe("1234567890123456");
    expect(item?.bedrooms).toBe(2);
    expect(item?.price).toBe(2400);
  });
  it("snippet ≤200 chars", () => {
    expect((item?.description_snippet ?? "").length).toBeLessThanOrEqual(200);
  });
});

describe("facebook_marketplace runExtraction", () => {
  it("captures search results", () => {
    const doc = loadFixture("search_results.html");
    const out = runExtraction(
      doc,
      "https://www.facebook.com/marketplace/vancouver/propertyrentals",
      new SeenCache(),
    );
    expect(out.kind).toBe("captured");
    if (out.kind !== "captured") throw new Error("unreachable");
    expect(out.payload.source).toBe(SOURCE);
    expect(out.payload.schema_version).toBe(SCHEMA_VERSION);
  });

  it("does NOT activate on non-marketplace paths", () => {
    const doc = new JSDOM("<!doctype html><html><body></body></html>").window.document;
    const out = runExtraction(doc, "https://www.facebook.com/profile/me", new SeenCache());
    expect(out.kind).toBe("skipped");
  });
});
