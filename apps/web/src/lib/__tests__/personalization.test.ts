// Issue #125 — tests for the personalization bias.

import { applyBias, bias, buildProfile, MAX_BIAS } from "@/src/lib/personalization";
import type { NormalizedListing } from "@/src/api/types";
import type { SnapshotMap } from "@/src/storage/listingSnapshots";

function listing(o: Partial<NormalizedListing> & { id: string }): NormalizedListing {
  return {
    id: o.id,
    canonical_id: o.id,
    source: o.source ?? "craigslist",
    source_url: "https://example.com/" + o.id,
    source_listing_id: o.id,
    title: "L",
    address: null,
    address_normalized: null,
    lat: null,
    lon: null,
    bedrooms: o.bedrooms ?? null,
    bathrooms: null,
    price_cad: o.price_cad ?? null,
    pets_allowed: null,
    furnished: null,
    available_date: null,
    posted_at: new Date().toISOString(),
    last_seen_at: new Date().toISOString(),
    photos: [],
    description_snippet: null,
    school_catchments: { elementary: null, middle: null, secondary: null },
    nearest_transit: null,
    walkscore: null,
    raw_metadata: {},
    neighborhood: (o as { neighborhood?: string | null }).neighborhood ?? null,
    match_score: o.match_score ?? 50,
  };
}

describe("buildProfile", () => {
  test("empty actions produces no-signal profile", () => {
    const p = buildProfile({}, {});
    expect(p.hasSignal).toBe(false);
  });

  test("a saved listing adds positive weight to its features", () => {
    const snapshots: SnapshotMap = {
      a: { source: "livrent", bedrooms: 2, price_bucket: 3000, neighborhood: "Kits" },
    };
    const p = buildProfile({ a: { saved: true } }, snapshots);
    expect(p.hasSignal).toBe(true);
    expect(p.source.livrent).toBeGreaterThan(0);
    expect(p.bedrooms["2"]).toBeGreaterThan(0);
  });

  test("a hidden listing adds negative weight", () => {
    const snapshots: SnapshotMap = {
      h: { source: "rew", bedrooms: 1, price_bucket: 1500, neighborhood: null },
    };
    const p = buildProfile({ h: { hidden: true } }, snapshots);
    expect(p.source.rew).toBeLessThan(0);
    expect(p.bedrooms["1"]).toBeLessThan(0);
  });

  test("saves and hides counter each other", () => {
    const snapshots: SnapshotMap = {
      a: { source: "x", bedrooms: 2, price_bucket: 2500, neighborhood: null },
      b: { source: "x", bedrooms: 2, price_bucket: 2500, neighborhood: null },
    };
    const p = buildProfile({ a: { saved: true }, b: { hidden: true } }, snapshots);
    expect(p.source.x).toBe(0);
  });
});

describe("bias", () => {
  test("returns zero when profile has no signal", () => {
    const p = buildProfile({}, {});
    expect(bias(listing({ id: "x" }), p).delta).toBe(0);
  });

  test("positive bias when listing matches saved features", () => {
    const snapshots: SnapshotMap = {
      a: { source: "livrent", bedrooms: 2, price_bucket: 3000, neighborhood: "Kits" },
      b: { source: "livrent", bedrooms: 2, price_bucket: 3000, neighborhood: "Kits" },
      c: { source: "livrent", bedrooms: 2, price_bucket: 3000, neighborhood: "Kits" },
      d: { source: "livrent", bedrooms: 2, price_bucket: 3000, neighborhood: "Kits" },
    };
    const p = buildProfile(
      { a: { saved: true }, b: { saved: true }, c: { saved: true }, d: { saved: true } },
      snapshots,
    );
    const target = listing({
      id: "t",
      source: "livrent",
      bedrooms: 2,
      price_cad: 3000,
    });
    (target as { neighborhood?: string }).neighborhood = "Kits";
    const r = bias(target, p);
    expect(r.delta).toBeGreaterThan(0);
    expect(r.reason).toBe("positive");
  });

  test("delta is clipped to MAX_BIAS in magnitude", () => {
    const snapshots: SnapshotMap = {};
    const actions: Record<string, { saved?: boolean }> = {};
    for (let i = 0; i < 100; i++) {
      const k = `k${i}`;
      snapshots[k] = {
        source: "test",
        bedrooms: 2,
        price_bucket: 2500,
        neighborhood: "K",
      };
      actions[k] = { saved: true };
    }
    const p = buildProfile(actions, snapshots);
    const target = listing({ id: "x", source: "test", bedrooms: 2, price_cad: 2500 });
    (target as { neighborhood?: string }).neighborhood = "K";
    const r = bias(target, p);
    expect(r.delta).toBe(MAX_BIAS);
  });
});

describe("applyBias", () => {
  test("clipped to 0-100", () => {
    const snapshots: SnapshotMap = {};
    const actions: Record<string, { hidden?: boolean }> = {};
    for (let i = 0; i < 100; i++) {
      const k = `k${i}`;
      snapshots[k] = { source: "x", bedrooms: 2, price_bucket: 2500, neighborhood: null };
      actions[k] = { hidden: true };
    }
    const profile = buildProfile(actions, snapshots);
    const low = listing({ id: "z", source: "x", bedrooms: 2, price_cad: 2500, match_score: 2 });
    const out = applyBias(low, profile);
    expect(out.match_score).toBeGreaterThanOrEqual(0);
  });

  test("appends a hint to match_explanation", () => {
    const snapshots: SnapshotMap = {
      a: { source: "test", bedrooms: 2, price_bucket: 2500, neighborhood: null },
      b: { source: "test", bedrooms: 2, price_bucket: 2500, neighborhood: null },
      c: { source: "test", bedrooms: 2, price_bucket: 2500, neighborhood: null },
      d: { source: "test", bedrooms: 2, price_bucket: 2500, neighborhood: null },
    };
    const profile = buildProfile(
      { a: { saved: true }, b: { saved: true }, c: { saved: true }, d: { saved: true } },
      snapshots,
    );
    const target = listing({ id: "t", source: "test", bedrooms: 2, price_cad: 2500 });
    target.match_explanation = "in your price range";
    const out = applyBias(target, profile);
    expect(out.match_explanation).toContain("like ones you've saved");
  });
});
