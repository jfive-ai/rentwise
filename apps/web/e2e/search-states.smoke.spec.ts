import { test, expect } from "@playwright/test";
import fixture from "../__fixtures__/search_response.json";

// Bug 1 (today's report): when the only enabled adapter (Craigslist) returns
// 403 from a non-residential IP, the API responds 200 with total=0 and
// source_health.craigslist.status="degraded" + last_error. The previous UI
// just said "No listings matched your filters", so the user couldn't tell
// the difference between "I'm searching wrong" and "the search is broken".
test.describe("Search states", () => {
  test("loading state shows a 'Searching…' indicator while /search is in flight", async ({
    page,
  }) => {
    let release: (() => void) | undefined;
    const inFlight = new Promise<void>((r) => {
      release = r;
    });
    await page.route("**/search", async (route) => {
      await inFlight;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(fixture),
      });
    });

    await page.goto("/");
    // Touch a filter so the page is hydrated (mirrors search.smoke.spec.ts).
    await page.getByRole("button", { name: "2", exact: true }).click();
    await page.getByRole("button", { name: "Search", exact: true }).click();

    // Two distinct "Searching…" affordances now appear together:
    // 1. Result-area skeleton (alert role, "Searching for listings").
    // 2. The button itself (its accessibility label flips from
    //    "Search" → "Searching…" with a spinner).
    // Pin both — they signal progress in different parts of the UI and
    // both regressed in the past when state failed to propagate.
    await expect(
      page.getByRole("alert", { name: "Searching for listings" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Searching…" }),
    ).toBeVisible();

    // Releasing the response transitions us out of loading.
    release!();
    await expect(page.getByText(/^5 listings$/)).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Searching…" }),
    ).toHaveCount(0);
  });

  test("adapter-failure banner names the source + first-line error", async ({
    page,
  }) => {
    await page.route("**/search", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          total: 0,
          listings: [],
          cache_status: "miss",
          unsupported_filters: [],
          source_health: {
            craigslist: {
              name: "craigslist",
              status: "degraded",
              last_successful_fetch: null,
              last_error:
                "Client error '403 Forbidden' for url 'https://vancouver.craigslist.org/search/apa?format=rss&hasPic=1'\nFor more information check: https://developer.mozilla.org/...",
            },
          },
        }),
      });
    });

    await page.goto("/");
    await page.getByRole("button", { name: "2", exact: true }).click();
    await page.getByRole("button", { name: "Search", exact: true }).click();

    await expect(
      page.getByText("Source unavailable: craigslist"),
    ).toBeVisible();
    await expect(
      page.getByText(/craigslist \(degraded\): Client error '403 Forbidden'/),
    ).toBeVisible();
    // The misleading "No listings matched your filters" copy is replaced
    // when every queried source is non-ok.
    await expect(
      page.getByText("Couldn't reach any source. See the banner above for details."),
    ).toBeVisible();
    await expect(
      page.getByText("No listings matched your filters."),
    ).toBeHidden();
  });

  test("Search with no filters set — state actually updates (regression: router.replace remount)", async ({
    page,
  }) => {
    // Critical regression: `router.replace` was unmounting+remounting
    // SearchScreen on every Search click, causing the in-flight search's
    // setState calls to commit to a torn-down instance. The user saw a
    // frozen "Set filters and press Search" empty state even though
    // POST /search returned 200. The fix swaps router.replace for raw
    // history.replaceState so the URL still updates without nuking the
    // component tree.
    await page.route("**/search", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          total: 0,
          listings: [],
          cache_status: "miss",
          unsupported_filters: [],
          source_health: {
            craigslist: {
              name: "craigslist",
              status: "degraded",
              last_successful_fetch: null,
              last_error: "403 Forbidden",
            },
          },
        }),
      });
    });

    await page.goto("/");
    // No filter touched. Click Search directly — this used to leave the
    // screen stuck in idle.
    await page.getByRole("button", { name: "Search", exact: true }).click();

    await expect(
      page.getByText("Source unavailable: craigslist"),
    ).toBeVisible();
    await expect(
      page.getByText("Set filters and press Search to find listings."),
    ).toBeHidden();
  });

  test("zero results with all sources ok keeps the original 'No listings matched' copy", async ({
    page,
  }) => {
    await page.route("**/search", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          total: 0,
          listings: [],
          cache_status: "miss",
          unsupported_filters: [],
          source_health: {
            craigslist: {
              name: "craigslist",
              status: "ok",
              last_successful_fetch: "2026-05-08T12:00:00Z",
              last_error: null,
            },
          },
        }),
      });
    });

    await page.goto("/");
    await page.getByRole("button", { name: "2", exact: true }).click();
    await page.getByRole("button", { name: "Search", exact: true }).click();

    // Original copy preserved when adapters are healthy and just had no
    // matches — that's an honest "no results" rather than a failure.
    await expect(
      page.getByText("No listings matched your filters."),
    ).toBeVisible();
    // No adapter-failure banner.
    await expect(
      page.getByText(/Source unavailable/),
    ).toHaveCount(0);
  });
});
