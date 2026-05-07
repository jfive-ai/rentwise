/**
 * liv.rent content script. Listings live under `/listings/<id>`; the
 * `/listings/vancouver` URL (or `/listings/<city>?...`) is the search.
 */

import {
  absoluteUrl,
  attr,
  parseBathrooms,
  parseBedrooms,
  parsePrice,
  parseSqft,
  SeenCache,
  showBanner,
  snippet,
  text,
} from "@/content/base";
import {
  CapturePayloadSchema,
  type CaptureListing,
  type CapturePayload,
  type PageType,
} from "@/schemas/capture";

export const SOURCE = "liv_rent" as const;
export const SCHEMA_VERSION = "2026-05-07";

export const SELECTORS = {
  searchResultsContainer: '[data-testid="listings-grid"], .listings-grid, main',
  searchResultsCard: '[data-testid="listing-card"], a.listing-card',
  cardTitle: '[data-testid="listing-card-title"], .listing-card__title',
  cardPrice: '[data-testid="listing-card-price"], .listing-card__price',
  cardBeds: '[data-testid="listing-card-beds"], .listing-card__beds',
  cardLink: 'a',
  cardThumb: 'img',
  detailContainer: '[data-testid="listing-detail"], main',
  detailTitle: 'h1',
  detailPrice: '[data-testid="listing-price"], .listing__price',
  detailBeds: '[data-testid="listing-beds"], .listing__beds',
  detailBaths: '[data-testid="listing-baths"], .listing__baths',
  detailSqft: '[data-testid="listing-sqft"], .listing__sqft',
  detailNeighborhood: '[data-testid="listing-neighborhood"], .listing__neighborhood',
  detailDescription: '[data-testid="listing-description"], .listing__description',
  detailPhotos: '[data-testid="listing-gallery"] img, .listing__gallery img',
} as const;

const LISTINGS_CITIES = new Set([
  "vancouver",
  "burnaby",
  "richmond",
  "surrey",
  "north-vancouver",
  "west-vancouver",
  "coquitlam",
  "new-westminster",
]);

export function classifyPage(pathname: string): PageType | null {
  // /listings/<id>            → detail (id is alphanumeric, not a city)
  // /listings/<city> or /listings/<city>/...  → search
  const m = pathname.match(/^\/listings\/([^/]+)/);
  if (!m) return null;
  const slug = m[1];
  if (slug === undefined) return null;
  if (LISTINGS_CITIES.has(slug)) return "search_results";
  // Anything else under /listings/ we treat as a detail page.
  return "listing_detail";
}

export function parseListingId(url: string): string | null {
  try {
    const u = new URL(url);
    const m = u.pathname.match(/^\/listings\/([^/]+)/);
    if (!m) return null;
    const slug = m[1];
    if (slug === undefined || LISTINGS_CITIES.has(slug)) return null;
    return slug;
  } catch {
    return null;
  }
}

export function extractFromSearchResults(doc: Document, baseUrl: string): CaptureListing[] {
  const cards = doc.querySelectorAll(SELECTORS.searchResultsCard);
  const out: CaptureListing[] = [];
  for (const card of Array.from(cards)) {
    const linkEl = card.matches("a") ? card : card.querySelector(SELECTORS.cardLink);
    const href = attr(linkEl, "href");
    const url = absoluteUrl(href, baseUrl);
    if (!url) continue;
    const id = parseListingId(url);
    if (!id) continue;
    const title = text(card.querySelector(SELECTORS.cardTitle));
    const priceRaw = text(card.querySelector(SELECTORS.cardPrice));
    const bedsRaw = text(card.querySelector(SELECTORS.cardBeds));
    const thumb = absoluteUrl(attr(card.querySelector(SELECTORS.cardThumb), "src"), baseUrl);
    out.push({
      source_listing_id: id,
      url,
      title: title ?? null,
      price: parsePrice(priceRaw),
      bedrooms: parseBedrooms(bedsRaw),
      bathrooms: null,
      sqft: null,
      neighborhood: null,
      posted_at: null,
      thumbnail_url: thumb ?? null,
      photo_urls: [],
      description_snippet: null,
      capture_method: "extension",
      page_type: "search_results",
    });
  }
  return out;
}

export function extractFromDetail(doc: Document, baseUrl: string): CaptureListing | null {
  const id = parseListingId(baseUrl);
  if (!id) return null;
  const container = doc.querySelector(SELECTORS.detailContainer);
  if (!container) return null;
  const title = text(container.querySelector(SELECTORS.detailTitle));
  const priceRaw = text(container.querySelector(SELECTORS.detailPrice));
  const bedsRaw = text(container.querySelector(SELECTORS.detailBeds));
  const bathsRaw = text(container.querySelector(SELECTORS.detailBaths));
  const sqftRaw = text(container.querySelector(SELECTORS.detailSqft));
  const neighborhood = text(container.querySelector(SELECTORS.detailNeighborhood));
  const descRaw = text(container.querySelector(SELECTORS.detailDescription));
  const photos: string[] = [];
  for (const img of Array.from(container.querySelectorAll(SELECTORS.detailPhotos))) {
    const src = absoluteUrl(attr(img, "src"), baseUrl);
    if (src) photos.push(src);
  }
  return {
    source_listing_id: id,
    url: baseUrl,
    title: title ?? null,
    price: parsePrice(priceRaw),
    bedrooms: parseBedrooms(bedsRaw),
    bathrooms: parseBathrooms(bathsRaw),
    sqft: parseSqft(sqftRaw),
    neighborhood: neighborhood ?? null,
    posted_at: null,
    thumbnail_url: photos[0] ?? null,
    photo_urls: photos,
    description_snippet: snippet(descRaw),
    capture_method: "extension",
    page_type: "listing_detail",
  };
}

export type RunResult =
  | { kind: "skipped"; reason: string }
  | { kind: "captured"; payload: CapturePayload }
  | { kind: "degraded"; reason: string };

export function runExtraction(
  doc: Document,
  pageUrl: string,
  seen: SeenCache,
  now: Date = new Date(),
): RunResult {
  let pathname: string;
  try {
    pathname = new URL(pageUrl).pathname;
  } catch {
    return { kind: "skipped", reason: "bad_url" };
  }
  const pageType = classifyPage(pathname);
  if (!pageType) return { kind: "skipped", reason: "unmatched_path" };

  let listings: CaptureListing[];
  if (pageType === "search_results") {
    if (!doc.querySelector(SELECTORS.searchResultsContainer)) {
      return { kind: "degraded", reason: "search_container_missing" };
    }
    listings = extractFromSearchResults(doc, pageUrl);
    if (listings.length === 0) return { kind: "skipped", reason: "no_cards" };
  } else {
    const one = extractFromDetail(doc, pageUrl);
    if (!one) return { kind: "degraded", reason: "detail_container_missing" };
    listings = [one];
  }

  const fresh = seen.filterNew(listings);
  if (fresh.length === 0) return { kind: "skipped", reason: "all_seen" };

  const payload: CapturePayload = {
    source: SOURCE,
    captured_at: now.toISOString(),
    page_type: pageType,
    page_url: pageUrl,
    schema_version: SCHEMA_VERSION,
    listings: fresh,
  };
  CapturePayloadSchema.parse(payload);
  return { kind: "captured", payload };
}

declare const chrome: typeof globalThis extends { chrome: infer C } ? C : never;

const seen = new SeenCache();

async function bootstrap(): Promise<void> {
  if (typeof chrome === "undefined" || !chrome?.runtime?.sendMessage) return;
  const { sendCapture, sendHealth } = await import("@/content/capture-client");
  const result = runExtraction(document, window.location.href, seen);
  if (result.kind === "captured") {
    const resp = await sendCapture(result.payload);
    if (resp.ok && resp.response.accepted > 0) {
      showBanner(`✓ RentWise captured ${resp.response.accepted} listing(s)`);
    }
  } else if (result.kind === "degraded") {
    await sendHealth({
      source: SOURCE,
      schema_version: SCHEMA_VERSION,
      status: "degraded",
      reason: result.reason,
    });
  }
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  setTimeout(() => {
    void bootstrap();
  }, 0);
}
