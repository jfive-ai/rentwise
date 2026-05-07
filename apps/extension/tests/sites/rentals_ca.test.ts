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
} from "@/content/sites/rentals_ca";

function loadFixture(name: string): Document {
  const path = resolve(__dirname, "..", "fixtures", "rentals_ca", name);
  const html = readFileSync(path, "utf8");
  return new JSDOM(html).window.document;
}

describe("rentals_ca classifyPage", () => {
  it.each([
    ["/vancouver", "search_results"],
    ["/vancouver/", "search_results"],
    ["/vancouver/mount-pleasant", "search_results"],
    ["/vancouver/listing/1234-cambie-st", "listing_detail"],
    ["/about", "search_results"], // single segment matches search root pattern; OK — content guard catches empty
    // Detail subpaths (e.g. /listing/<slug>/photos) still classify as listing_detail —
    // the parseListingId fallback + container guard handle the rest.
    ["/vancouver/listing/foo/extra", "listing_detail"],
  ])("classifies %s", (path, expected) => {
    expect(classifyPage(path)).toBe(expected);
  });
});

describe("rentals_ca parseListingId", () => {
  it("pulls slug from a relative-rendered absolute URL", () => {
    expect(parseListingId("https://rentals.ca/vancouver/listing/1234-cambie-st-1234")).toBe(
      "1234-cambie-st-1234",
    );
  });
  it("returns null for non-listing URLs", () => {
    expect(parseListingId("https://rentals.ca/vancouver")).toBeNull();
  });
});

describe("rentals_ca extractFromSearchResults", () => {
  const doc = loadFixture("search_results.html");
  const baseUrl = "https://rentals.ca/vancouver";
  const items = extractFromSearchResults(doc, baseUrl);

  it("captures every visible card", () => {
    expect(items).toHaveLength(3);
  });

  it("resolves relative hrefs to absolute URLs", () => {
    expect(items[0]?.url).toBe("https://rentals.ca/vancouver/listing/1234-cambie-st-1234");
    expect(items[1]?.url).toBe("https://rentals.ca/vancouver/listing/4567-w-broadway");
  });

  it("parses price and bedrooms", () => {
    expect(items[0]?.price).toBe(2750);
    expect(items[0]?.bedrooms).toBe(2);
    expect(items[1]?.bedrooms).toBe(0); // studio
    expect(items[2]?.price).toBe(4200);
  });

  it("captures neighborhood from the card", () => {
    expect(items[0]?.neighborhood).toBe("Mount Pleasant");
    expect(items[1]?.neighborhood).toBe("Kitsilano");
  });

  it("does NOT capture descriptions on search-results pages", () => {
    for (const item of items) expect(item.description_snippet).toBeNull();
  });

  it("tags every item as search_results / extension", () => {
    for (const item of items) {
      expect(item.page_type).toBe("search_results");
      expect(item.capture_method).toBe("extension");
    }
  });
});

describe("rentals_ca extractFromDetail", () => {
  const doc = loadFixture("listing_detail.html");
  const baseUrl = "https://rentals.ca/vancouver/listing/1234-cambie-st-1234";
  const item = extractFromDetail(doc, baseUrl);

  it("returns a single populated listing", () => {
    expect(item).not.toBeNull();
    expect(item?.source_listing_id).toBe("1234-cambie-st-1234");
  });

  it("parses bedrooms, bathrooms, sqft", () => {
    expect(item?.bedrooms).toBe(2);
    expect(item?.bathrooms).toBe(1.5);
    expect(item?.sqft).toBe(820);
  });

  it("captures snippet capped at 200 chars", () => {
    expect(item?.description_snippet).not.toBeNull();
    expect(item?.description_snippet?.length).toBeLessThanOrEqual(200);
  });

  it("collects all photo URLs and absolutizes them", () => {
    expect(item?.photo_urls).toHaveLength(3);
    expect(item?.photo_urls[0]).toBe("https://rentals.ca/images/photos/1.jpg");
    expect(item?.photo_urls[2]).toBe("https://cdn.rentals.ca/images/photos/3.jpg");
  });
});

describe("rentals_ca runExtraction", () => {
  it("produces a captured payload from a search-results page", () => {
    const doc = loadFixture("search_results.html");
    const seen = new SeenCache();
    const out = runExtraction(doc, "https://rentals.ca/vancouver", seen, new Date("2026-05-07T12:00:00Z"));
    expect(out.kind).toBe("captured");
    if (out.kind !== "captured") throw new Error("unreachable");
    expect(out.payload.source).toBe(SOURCE);
    expect(out.payload.schema_version).toBe(SCHEMA_VERSION);
    expect(out.payload.page_type).toBe("search_results");
    expect(out.payload.listings).toHaveLength(3);
  });

  it("filters previously-seen listings (idempotency)", () => {
    const doc = loadFixture("search_results.html");
    const seen = new SeenCache();
    const first = runExtraction(doc, "https://rentals.ca/vancouver", seen);
    expect(first.kind).toBe("captured");
    const second = runExtraction(doc, "https://rentals.ca/vancouver", seen);
    expect(second.kind).toBe("skipped");
  });

  it("emits degraded when search container is missing", () => {
    const doc = new JSDOM("<!doctype html><html><body><p>nothing here</p></body></html>").window.document;
    const out = runExtraction(doc, "https://rentals.ca/vancouver", new SeenCache());
    expect(out.kind).toBe("degraded");
    if (out.kind === "degraded") expect(out.reason).toBe("search_container_missing");
  });

  it("emits degraded when detail container is missing on a detail URL", () => {
    const doc = new JSDOM("<!doctype html><html><body></body></html>").window.document;
    const out = runExtraction(
      doc,
      "https://rentals.ca/vancouver/listing/1234-cambie-st",
      new SeenCache(),
    );
    expect(out.kind).toBe("degraded");
    if (out.kind === "degraded") expect(out.reason).toBe("detail_container_missing");
  });

  it("skips unknown URL shapes (e.g. deep paths the patterns don't match)", () => {
    const doc = new JSDOM("<!doctype html><html><body></body></html>").window.document;
    const out = runExtraction(
      doc,
      "https://rentals.ca/blog/posts/2024/why-we-built-this",
      new SeenCache(),
    );
    expect(out.kind).toBe("skipped");
  });
});
