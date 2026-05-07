/**
 * Source registry for the "Search across sources" launcher.
 *
 * Each source declares (a) a stable id matching the extension's
 * `SourceId` enum (kept in sync by hand — they're separate npm projects)
 * and (b) a pure `urlBuilder` that translates a NormalizedQuery into the
 * source's public search URL. Builders return `{ url, unsupported }`
 * where `unsupported` lists query fields that this source's URL params
 * can't express; the launcher surfaces these as a hint per the design
 * spec § 8.1.
 *
 * URL parameter names are observed from the live sites' search forms
 * and may need adjusting after a manual fixture refresh — see
 * `apps/extension/README.md` § Fixture refresh.
 */

import type { NormalizedQuery } from "@/src/api/types";

export type SourceId =
  | "rentals_ca"
  | "padmapper"
  | "zumper"
  | "rew_ca"
  | "liv_rent"
  | "facebook_marketplace";

export interface BuiltSearchUrl {
  url: string;
  unsupported: string[];
}

export interface SourceDef {
  id: SourceId;
  label: string;
  build: (query: NormalizedQuery) => BuiltSearchUrl | null;
}

const VANCOUVER_NEIGHBORHOOD_SLUGS: Record<string, string> = {
  "Coal Harbour": "coal-harbour",
  "Commercial Drive": "commercial-drive",
  Downtown: "downtown",
  Dunbar: "dunbar",
  "East Vancouver": "east-vancouver",
  Fairview: "fairview",
  "False Creek": "false-creek",
  Gastown: "gastown",
  "Grandview-Woodland": "grandview-woodland",
  Kerrisdale: "kerrisdale",
  Kitsilano: "kitsilano",
  Marpole: "marpole",
  "Mount Pleasant": "mount-pleasant",
  Oakridge: "oakridge",
  "Point Grey": "point-grey",
  "Riley Park": "riley-park",
  Shaughnessy: "shaughnessy",
  "South Cambie": "south-cambie",
  "South Granville": "south-granville",
  Strathcona: "strathcona",
  Sunset: "sunset",
  "West End": "west-end",
  "West Point Grey": "west-point-grey",
  Yaletown: "yaletown",
};

function pickNeighborhoodSlug(query: NormalizedQuery): string | null {
  if (query.neighborhoods.length === 0) return null;
  // URL params can't represent multiple neighborhoods uniformly across all six
  // sources. Pick the first; the user refines the rest on the open page.
  const first = query.neighborhoods[0];
  if (first === undefined) return null;
  return VANCOUVER_NEIGHBORHOOD_SLUGS[first] ?? null;
}

function qs(params: URLSearchParams): string {
  const s = params.toString();
  return s.length === 0 ? "" : `?${s}`;
}

function unsupportedFields(query: NormalizedQuery, supported: Set<string>): string[] {
  const present: string[] = [];
  if (query.bedrooms_min != null && !supported.has("bedrooms_min")) present.push("bedrooms_min");
  if (query.bedrooms_max != null && !supported.has("bedrooms_max")) present.push("bedrooms_max");
  if (query.price_min != null && !supported.has("price_min")) present.push("price_min");
  if (query.price_max != null && !supported.has("price_max")) present.push("price_max");
  if (query.neighborhoods.length > 0 && !supported.has("neighborhoods")) present.push("neighborhoods");
  if (query.pets !== "any" && !supported.has("pets")) present.push("pets");
  if (query.furnished !== "any" && !supported.has("furnished")) present.push("furnished");
  if (query.free_text_keywords.length > 0 && !supported.has("free_text_keywords"))
    present.push("free_text_keywords");
  return present;
}

function build_rentals_ca(query: NormalizedQuery): BuiltSearchUrl {
  const slug = pickNeighborhoodSlug(query);
  const path = slug ? `/vancouver/${slug}` : "/vancouver";
  const params = new URLSearchParams();
  if (query.bedrooms_min != null) params.set("bedrooms", String(query.bedrooms_min));
  if (query.price_min != null) params.set("min_price", String(query.price_min));
  if (query.price_max != null) params.set("max_price", String(query.price_max));
  if (query.pets === "ok" || query.pets === "required") params.set("pets", "true");
  const supported = new Set([
    "bedrooms_min",
    "price_min",
    "price_max",
    "neighborhoods",
    "pets",
  ]);
  return {
    url: `https://rentals.ca${path}${qs(params)}`,
    unsupported: unsupportedFields(query, supported),
  };
}

function build_padmapper(query: NormalizedQuery): BuiltSearchUrl {
  const params = new URLSearchParams();
  if (query.bedrooms_min != null) params.set("min_bedrooms", String(query.bedrooms_min));
  if (query.bedrooms_max != null) params.set("max_bedrooms", String(query.bedrooms_max));
  if (query.price_min != null) params.set("min_price", String(query.price_min));
  if (query.price_max != null) params.set("max_price", String(query.price_max));
  const supported = new Set([
    "bedrooms_min",
    "bedrooms_max",
    "price_min",
    "price_max",
  ]);
  return {
    url: `https://www.padmapper.com/apartments/vancouver-bc${qs(params)}`,
    unsupported: unsupportedFields(query, supported),
  };
}

function build_zumper(query: NormalizedQuery): BuiltSearchUrl {
  const params = new URLSearchParams();
  if (query.bedrooms_min != null) params.set("bedrooms-min", String(query.bedrooms_min));
  if (query.price_min != null) params.set("price-min", String(query.price_min));
  if (query.price_max != null) params.set("price-max", String(query.price_max));
  const supported = new Set(["bedrooms_min", "price_min", "price_max"]);
  return {
    url: `https://www.zumper.com/apartments-for-rent/vancouver-bc${qs(params)}`,
    unsupported: unsupportedFields(query, supported),
  };
}

function build_rew_ca(query: NormalizedQuery): BuiltSearchUrl {
  const slug = pickNeighborhoodSlug(query);
  const path = slug
    ? `/properties/areas/vancouver-bc/neighbourhoods/${slug}/type/rent`
    : `/properties/areas/vancouver-bc/type/rent`;
  const params = new URLSearchParams();
  if (query.bedrooms_min != null) params.set("minbeds", String(query.bedrooms_min));
  if (query.price_min != null) params.set("minprice", String(query.price_min));
  if (query.price_max != null) params.set("maxprice", String(query.price_max));
  const supported = new Set([
    "bedrooms_min",
    "price_min",
    "price_max",
    "neighborhoods",
  ]);
  return {
    url: `https://www.rew.ca${path}${qs(params)}`,
    unsupported: unsupportedFields(query, supported),
  };
}

function build_liv_rent(query: NormalizedQuery): BuiltSearchUrl {
  const params = new URLSearchParams();
  if (query.bedrooms_min != null) params.set("min_beds", String(query.bedrooms_min));
  if (query.price_min != null) params.set("min_price", String(query.price_min));
  if (query.price_max != null) params.set("max_price", String(query.price_max));
  if (query.pets === "ok" || query.pets === "required") params.set("pets", "1");
  const supported = new Set(["bedrooms_min", "price_min", "price_max", "pets"]);
  return {
    url: `https://liv.rent/listings/vancouver${qs(params)}`,
    unsupported: unsupportedFields(query, supported),
  };
}

function build_facebook_marketplace(query: NormalizedQuery): BuiltSearchUrl {
  const params = new URLSearchParams();
  if (query.price_min != null) params.set("minPrice", String(query.price_min));
  if (query.price_max != null) params.set("maxPrice", String(query.price_max));
  if (query.bedrooms_min != null) params.set("minBedrooms", String(query.bedrooms_min));
  if (query.bedrooms_max != null) params.set("maxBedrooms", String(query.bedrooms_max));
  const supported = new Set([
    "price_min",
    "price_max",
    "bedrooms_min",
    "bedrooms_max",
  ]);
  return {
    url: `https://www.facebook.com/marketplace/vancouver/propertyrentals${qs(params)}`,
    unsupported: unsupportedFields(query, supported),
  };
}

export const SOURCES: SourceDef[] = [
  { id: "rentals_ca", label: "Rentals.ca", build: build_rentals_ca },
  { id: "padmapper", label: "PadMapper", build: build_padmapper },
  { id: "zumper", label: "Zumper", build: build_zumper },
  { id: "rew_ca", label: "REW.ca", build: build_rew_ca },
  { id: "liv_rent", label: "liv.rent", build: build_liv_rent },
  {
    id: "facebook_marketplace",
    label: "Facebook Marketplace",
    build: build_facebook_marketplace,
  },
];
