/**
 * Rentals.ca content script.
 *
 * Activated by the manifest on https://rentals.ca/* — but this script
 * only acts on URLs matching the search/detail patterns below. All other
 * pages are a no-op.
 *
 * Selectors are versioned together with the parsing logic. When a
 * required selector returns nothing on a page that *should* have it, we
 * fire one degraded ping and bail — silent loss is the failure mode we
 * are most trying to avoid (per `docs/superpowers/specs/2026-05-07-phase-3-launcher-extension-design.md` § 5.3).
 *
 * Fixtures: synthetic HTML in `tests/fixtures/rentals_ca/`. To refresh
 * against production, save the rendered HTML by hand from a real page —
 * see `apps/extension/README.md`. We do not auto-fetch the live site.
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

export const SOURCE = "rentals_ca" as const;
export const SCHEMA_VERSION = "2026-05-07";

export const SELECTORS = {
  // Search-results page
  searchResultsContainer: '[data-cy="listings-grid"], .listings-grid, main',
  searchResultsCard: 'a[data-cy="listing-card"], a.listing-card',
  cardTitle: '[data-cy="listing-card-title"], .listing-card__title',
  cardPrice: '[data-cy="listing-card-price"], .listing-card__price',
  cardBeds: '[data-cy="listing-card-beds"], .listing-card__beds',
  cardNeighborhood: '[data-cy="listing-card-neighborhood"], .listing-card__neighborhood',
  cardThumb: 'img',
  // Listing-detail page
  detailContainer: '[data-cy="listing-detail"], main[role="main"]',
  detailTitle: 'h1',
  detailPrice: '[data-cy="listing-price"], .listing__price',
  detailBeds: '[data-cy="listing-beds"], .listing__beds',
  detailBaths: '[data-cy="listing-baths"], .listing__baths',
  detailSqft: '[data-cy="listing-sqft"], .listing__sqft',
  detailNeighborhood: '[data-cy="listing-neighborhood"], .listing__neighborhood',
  detailDescription: '[data-cy="listing-description"], .listing__description',
  detailPhotos: '[data-cy="listing-gallery"] img, .listing__gallery img',
} as const;

/** Listing detail URLs look like https://rentals.ca/<city>/listing/<slug> */
const DETAIL_PATH_RE = /^\/[^/]+\/listing\/[^/]+/;
/** Search results live at https://rentals.ca/<city>?... or /<city>/<neighborhood>?... */
const SEARCH_PATH_RE = /^\/[^/]+(\/[^/]+)?\/?$/;

export function classifyPage(pathname: string): PageType | null {
  if (DETAIL_PATH_RE.test(pathname)) return "listing_detail";
  // search includes the city root and any neighborhood subpath; exclude /listing/...
  if (pathname.startsWith("/")) {
    if (DETAIL_PATH_RE.test(pathname)) return null;
    if (SEARCH_PATH_RE.test(pathname)) return "search_results";
  }
  return null;
}

/** Parse the source_listing_id from a Rentals.ca listing URL. */
export function parseListingId(url: string): string | null {
  try {
    const u = new URL(url);
    const m = u.pathname.match(/\/listing\/([^/]+)/);
    return m ? (m[1] ?? null) : null;
  } catch {
    return null;
  }
}

export function extractFromSearchResults(doc: Document, baseUrl: string): CaptureListing[] {
  const cards = doc.querySelectorAll(SELECTORS.searchResultsCard);
  const out: CaptureListing[] = [];
  for (const card of Array.from(cards)) {
    const href = attr(card, "href");
    const url = absoluteUrl(href, baseUrl);
    if (!url) continue;
    const id = parseListingId(url);
    if (!id) continue;
    const title = text(card.querySelector(SELECTORS.cardTitle));
    const priceRaw = text(card.querySelector(SELECTORS.cardPrice));
    const bedsRaw = text(card.querySelector(SELECTORS.cardBeds));
    const neighborhood = text(card.querySelector(SELECTORS.cardNeighborhood));
    const thumb = absoluteUrl(attr(card.querySelector(SELECTORS.cardThumb), "src"), baseUrl);
    out.push({
      source_listing_id: id,
      url,
      title: title ?? null,
      price: parsePrice(priceRaw),
      bedrooms: parseBedrooms(bedsRaw),
      bathrooms: null,
      sqft: null,
      neighborhood: neighborhood ?? null,
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

/**
 * Run extraction on the supplied document. Pure / deterministic — the
 * `seen` cache is passed in so tests can assert idempotency.
 */
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
    if (listings.length === 0) {
      // The container exists but no cards rendered — could be a legitimately
      // empty result page. Surface as skipped, not degraded.
      return { kind: "skipped", reason: "no_cards" };
    }
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
  // Throw early in dev if the payload doesn't match the shared schema.
  CapturePayloadSchema.parse(payload);
  return { kind: "captured", payload };
}

// ------------------------------------------------------------------
// Browser-side bootstrap. Skipped under jsdom (no chrome.runtime).
// ------------------------------------------------------------------

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
  // document_idle is set in manifest; still defer to next tick so SPA
  // hydration has a chance.
  setTimeout(() => {
    void bootstrap();
  }, 0);
}
