import { emptyQuery, type NormalizedQuery } from "@/src/api/types";
import {
  decodeQueryFromParams,
  encodeQueryToParams,
  encodeQueryToString,
  hasAnyParams,
} from "@/src/lib/queryUrl";

const fullQuery = (): NormalizedQuery => ({
  bedrooms_min: 2,
  bedrooms_max: 3,
  price_min: 1500,
  price_max: 3500,
  neighborhoods: ["Kitsilano", "West End"],
  school_catchment: "Lord Byng",
  pets: "ok",
  furnished: "no",
  available_after: "2026-06-01",
  transit_max_walk_minutes: 10,
  free_text_keywords: ["balcony", "in-suite laundry"],
});

describe("encodeQueryToParams", () => {
  it("emits an empty string for the default empty query", () => {
    expect(encodeQueryToString(emptyQuery())).toBe("");
  });

  it("skips pets='any' and furnished='any'", () => {
    const p = encodeQueryToParams({ ...emptyQuery(), bedrooms_min: 2 });
    expect(p.has("pets")).toBe(false);
    expect(p.has("furnished")).toBe(false);
    expect(p.get("bedrooms_min")).toBe("2");
  });

  it("encodes arrays as comma-separated values", () => {
    const p = encodeQueryToParams({
      ...emptyQuery(),
      neighborhoods: ["A", "B"],
      free_text_keywords: ["k1", "k2"],
    });
    expect(p.get("neighborhoods")).toBe("A,B");
    expect(p.get("free_text_keywords")).toBe("k1,k2");
  });
});

describe("decodeQueryFromParams", () => {
  it("returns emptyQuery() for empty params", () => {
    expect(decodeQueryFromParams(new URLSearchParams())).toEqual(emptyQuery());
  });

  it("ignores unknown keys and malformed numbers", () => {
    const p = new URLSearchParams("bedrooms_min=abc&unknown_thing=xyz");
    expect(decodeQueryFromParams(p)).toEqual(emptyQuery());
  });

  it("restores valid scalars and arrays", () => {
    const p = new URLSearchParams(
      "bedrooms_min=2&price_max=3000&neighborhoods=Kitsilano,West+End&pets=ok",
    );
    const q = decodeQueryFromParams(p);
    expect(q.bedrooms_min).toBe(2);
    expect(q.price_max).toBe(3000);
    expect(q.neighborhoods).toEqual(["Kitsilano", "West End"]);
    expect(q.pets).toBe("ok");
  });

  it("falls back to 'any' when pets/furnished is unknown", () => {
    const p = new URLSearchParams("pets=garbage&furnished=banana");
    const q = decodeQueryFromParams(p);
    expect(q.pets).toBe("any");
    expect(q.furnished).toBe("any");
  });

  it("accepts a Record<string,string|string[]> source (expo-router shape)", () => {
    const q = decodeQueryFromParams({
      bedrooms_min: "2",
      neighborhoods: "Kitsilano,West End",
      ignored: undefined,
    });
    expect(q.bedrooms_min).toBe(2);
    expect(q.neighborhoods).toEqual(["Kitsilano", "West End"]);
  });
});

describe("round-trip", () => {
  it("decode(encode(q)) === q for a fully-populated query", () => {
    const q = fullQuery();
    const round = decodeQueryFromParams(encodeQueryToParams(q));
    expect(round).toEqual(q);
  });

  it("decode(encode(empty)) === empty", () => {
    expect(decodeQueryFromParams(encodeQueryToParams(emptyQuery()))).toEqual(emptyQuery());
  });
});

describe("hasAnyParams", () => {
  it("is false for the empty query", () => {
    expect(hasAnyParams(emptyQuery())).toBe(false);
  });
  it("is true when any field is set", () => {
    expect(hasAnyParams({ ...emptyQuery(), bedrooms_min: 1 })).toBe(true);
    expect(hasAnyParams({ ...emptyQuery(), neighborhoods: ["X"] })).toBe(true);
  });
});
