/**
 * Facebook Marketplace content script.
 *
 * Per `docs/legal.md` § "Facebook Marketplace": this is the highest-risk
 * source. The script:
 *   - activates ONLY on `/marketplace/.../propertyrentals` search paths
 *     and on `/marketplace/item/<id>/` detail pages,
 *   - never reads cookies, login state, or messaging UI,
 *   - never auto-paginates, auto-scrolls, or navigates,
 *   - captures only listing-card content the user already sees on the
 *     rendered page.
 *
 * Facebook routinely obfuscates CSS class names. Selectors here use
 * structural tags + ARIA roles + data-testid heuristics; expect to
 * refresh fixtures and SELECTORS more often than for other sources.
 */

import {
  absoluteUrl,
  attr,
  parseBedrooms,
  parsePrice,
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

export const SOURCE = "facebook_marketplace" as const;
export const SCHEMA_VERSION = "2026-05-07";

export const SELECTORS = {
  // Marketplace search-results lists every property-rental card; FB uses
  // a generic role=feed structure with cards as role=article.
  searchResultsContainer: '[role="feed"], [role="main"]',
  searchResultsCard: '[role="article"], a[href*="/marketplace/item/"]',
  cardTitle: 'span[dir="auto"]',
  cardPrice: 'span[dir="auto"]',
  cardLink: 'a[href*="/marketplace/item/"]',
  cardThumb: 'img',
  detailContainer: '[role="main"]',
  detailTitle: 'h1, h2',
  detailPrice: '[data-testid="marketplace-price"], h1 + div',
  detailBeds: '[data-testid="marketplace-bedrooms"]',
  detailBaths: '[data-testid="marketplace-bathrooms"]',
  detailDescription: '[data-testid="marketplace-description"], [aria-label="Description"]',
  detailPhotos: '[role="img"] img, img[alt]',
} as const;

const SEARCH_PATH_RE = /^\/marketplace\/[^/]+\/propertyrentals/;
const DETAIL_PATH_RE = /^\/marketplace\/item\/\d+/;

export function classifyPage(pathname: string): PageType | null {
  if (DETAIL_PATH_RE.test(pathname)) return "listing_detail";
  if (SEARCH_PATH_RE.test(pathname)) return "search_results";
  return null;
}

export function parseListingId(url: string): string | null {
  try {
    const u = new URL(url);
    const m = u.pathname.match(/\/marketplace\/item\/(\d+)/);
    return m ? (m[1] ?? null) : null;
  } catch {
    return null;
  }
}

/** First descendant span whose text looks like a price (`$1,234` etc.). */
function findPriceSpan(card: Element): string | null {
  const spans = card.querySelectorAll('span[dir="auto"], span');
  for (const s of Array.from(spans)) {
    const t = s.textContent?.trim() ?? "";
    if (/^[CA$]?\$\s?\d/.test(t)) return t;
  }
  return null;
}

/** First non-price span — usually the title for marketplace cards. */
function findTitleSpan(card: Element): string | null {
  const spans = card.querySelectorAll('span[dir="auto"], span');
  for (const s of Array.from(spans)) {
    const t = s.textContent?.trim() ?? "";
    if (!t) continue;
    if (/^[CA$]?\$\s?\d/.test(t)) continue;
    if (t.length > 200) continue;
    return t;
  }
  return null;
}

export function extractFromSearchResults(doc: Document, baseUrl: string): CaptureListing[] {
  // Each marketplace card is an <a href="/marketplace/item/<id>/...">.
  const links = doc.querySelectorAll(SELECTORS.cardLink);
  const out: CaptureListing[] = [];
  const seenIds = new Set<string>();
  for (const link of Array.from(links)) {
    const href = attr(link, "href");
    const url = absoluteUrl(href, baseUrl);
    if (!url) continue;
    const id = parseListingId(url);
    if (!id || seenIds.has(id)) continue;
    seenIds.add(id);
    const card = link.closest('[role="article"]') ?? link;
    const title = findTitleSpan(card);
    const priceRaw = findPriceSpan(card);
    const thumb = absoluteUrl(attr(card.querySelector(SELECTORS.cardThumb), "src"), baseUrl);
    out.push({
      source_listing_id: id,
      url,
      title: title ?? null,
      price: parsePrice(priceRaw),
      bedrooms: null, // FB rarely surfaces beds on the card itself
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
  const priceRaw = text(container.querySelector(SELECTORS.detailPrice)) ?? findPriceSpan(container);
  const bedsRaw = text(container.querySelector(SELECTORS.detailBeds));
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
    bathrooms: null,
    sqft: null,
    neighborhood: null,
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
