import type { Page, Route } from "@playwright/test";

/**
 * Build an NDJSON body from a search-response-shaped fixture so e2e
 * tests can mock the streaming endpoint introduced in issue #113.
 *
 * Each event is one JSON object terminated by `\n`. The shape mirrors
 * apps/api/rentwise/aggregator/streaming.py.
 */
export interface SearchFixtureLike {
  listings: unknown[];
  total: number;
  cache_status: "fresh" | "stale" | "miss";
  unsupported_filters: string[];
  source_health: Record<string, unknown>;
}

export function searchStreamBody(f: SearchFixtureLike): string {
  const events: unknown[] = [
    { event: "started", adapters: ["craigslist"] },
    ...f.listings.map((data) => ({ event: "listing", data })),
    {
      event: "adapter_done",
      adapter: "craigslist",
      count: f.listings.length,
      status: "ok",
      error: null,
    },
    {
      event: "complete",
      total: f.total,
      cache_status: f.cache_status,
      unsupported_filters: f.unsupported_filters,
      source_health: f.source_health,
    },
  ];
  return events.map((e) => JSON.stringify(e)).join("\n") + "\n";
}

/**
 * Register both `/search` (legacy JSON, for Load-more) and `/search/stream`
 * (NDJSON, for fresh searches) routes for an e2e test.
 *
 * Most tests share this setup, so factor it here. If a test needs to
 * customize one specific request, register its own narrower route
 * BEFORE calling this helper — Playwright's route matching is LIFO,
 * so later registrations win.
 */
export async function mockSearch(
  page: Page,
  fixture: SearchFixtureLike,
): Promise<void> {
  await page.route("**/search/stream", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/x-ndjson",
      body: searchStreamBody(fixture),
    });
  });
  await page.route("**/search", async (route: Route) => {
    // The glob `**/search` matches /search exactly (Playwright globs are
    // segment-aware), so this won't shadow /search/stream.
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(fixture),
    });
  });
}
