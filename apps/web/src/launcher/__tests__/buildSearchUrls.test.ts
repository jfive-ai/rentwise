import { emptyQuery } from "@/src/api/types";
import { buildSearchUrls } from "@/src/launcher/buildSearchUrls";
import { SOURCES } from "@/src/launcher/sources";

describe("buildSearchUrls", () => {
  it("returns one plan per source for an empty query", () => {
    const plans = buildSearchUrls(emptyQuery());
    expect(plans).toHaveLength(SOURCES.length);
    const ids = plans.map((p) => p.id).sort();
    expect(ids).toEqual(SOURCES.map((s) => s.id).sort());
  });

  it("respects the enabled set", () => {
    const enabled = new Set(["rentals_ca", "padmapper"] as const);
    const plans = buildSearchUrls(emptyQuery(), enabled);
    expect(plans.map((p) => p.id).sort()).toEqual(["padmapper", "rentals_ca"]);
  });

  it("encodes price + bedrooms into per-source URL params where supported", () => {
    const q = {
      ...emptyQuery(),
      bedrooms_min: 2,
      price_min: 1500,
      price_max: 3000,
    };
    const plans = buildSearchUrls(q);
    const byId = Object.fromEntries(plans.map((p) => [p.id, p]));
    expect(byId.padmapper?.url).toContain("min_bedrooms=2");
    expect(byId.padmapper?.url).toContain("max_price=3000");
    expect(byId.zumper?.url).toContain("price-min=1500");
    expect(byId.rentals_ca?.url).toContain("bedrooms=2");
    expect(byId.facebook_marketplace?.url).toContain("minBedrooms=2");
  });

  it("flags unsupported filters per source", () => {
    const q = { ...emptyQuery(), free_text_keywords: ["balcony"] };
    const plans = buildSearchUrls(q);
    for (const plan of plans) {
      expect(plan.unsupported).toContain("free_text_keywords");
    }
  });

  it("does not list a filter as unsupported when its value is the no-op default", () => {
    // Empty query has pets="any" / furnished="any" — these should never count
    // as unsupported on any source.
    const plans = buildSearchUrls(emptyQuery());
    for (const plan of plans) {
      expect(plan.unsupported).not.toContain("pets");
      expect(plan.unsupported).not.toContain("furnished");
    }
  });

  it("uses the first selected neighborhood for sources whose URLs path-segment by neighborhood", () => {
    const q = { ...emptyQuery(), neighborhoods: ["Mount Pleasant", "Kitsilano"] };
    const plans = buildSearchUrls(q);
    const rentals = plans.find((p) => p.id === "rentals_ca");
    expect(rentals?.url).toContain("/vancouver/mount-pleasant");
    const rew = plans.find((p) => p.id === "rew_ca");
    expect(rew?.url).toContain("/neighbourhoods/mount-pleasant");
    // Sources that can't path-segment a neighborhood mark it as unsupported.
    const padmapper = plans.find((p) => p.id === "padmapper");
    expect(padmapper?.unsupported).toContain("neighborhoods");
  });

  it("emits valid URLs for every source", () => {
    const plans = buildSearchUrls(emptyQuery());
    for (const plan of plans) {
      expect(() => new URL(plan.url)).not.toThrow();
    }
  });
});
