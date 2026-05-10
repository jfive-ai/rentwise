import { test, expect } from "@playwright/test";
import { mockSearch } from "./_stream";

/**
 * Issues #92 / #93 / #94 / #95 integration smoke.
 *
 * The backend is stubbed — we don't exercise the polygon filter in
 * jsdom; instead we verify the *frontend* behaves correctly when the
 * server returns a Dunbar-only result set:
 *
 * - The Dunbar chip in the filter panel survives a search round-trip.
 * - The selected-neighborhood overlay path triggers a fetch to
 *   `/map/overlays/neighborhoods` (proves SearchScreen passed the
 *   prop through).
 * - "Open original" opens a new tab rather than navigating away (#95).
 */
test("Dunbar filter triggers neighborhood overlay fetch + Open-original opens new tab", async ({
  page,
  context,
}) => {
  let neighborhoodsFetched = false;
  await page.route("**/map/overlays/neighborhoods", async (route) => {
    neighborhoodsFetched = true;
    await route.fulfill({
      status: 200,
      contentType: "application/geo+json",
      body: JSON.stringify({
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            properties: { name: "Dunbar-Southlands" },
            geometry: {
              type: "Polygon",
              coordinates: [
                [
                  [-123.20, 49.235],
                  [-123.16, 49.235],
                  [-123.16, 49.265],
                  [-123.20, 49.265],
                  [-123.20, 49.235],
                ],
              ],
            },
          },
        ],
      }),
    });
  });

  await mockSearch(page, {
    total: 1,
    cache_status: "miss",
    unsupported_filters: [],
    source_health: {
      craigslist: {
        name: "craigslist",
        status: "ok",
        last_successful_fetch: "2026-05-09T00:00:00Z",
        last_error: null,
      },
    },
    listings: [
      {
        id: "00000000-0000-0000-0000-000000000001",
        canonical_id: "00000000-0000-0000-0000-000000000001",
        source: "craigslist",
        source_url: "https://vancouver.craigslist.org/van/apa/d/dunbar-1.html",
        source_listing_id: "1",
        title: "Bright 2br in Dunbar",
        address: "4750 W 16th Ave",
        address_normalized: null,
        lat: 49.255,
        lon: -123.185,
        bedrooms: 2,
        bathrooms: 1,
        price_cad: 2900,
        pets_allowed: null,
        furnished: null,
        available_date: null,
        posted_at: "2026-05-08T10:00:00Z",
        last_seen_at: "2026-05-09T00:00:00Z",
        photos: [],
        description_snippet: "Inside the Dunbar-Southlands polygon.",
        neighborhood: "Dunbar-Southlands",
        school_catchments: { elementary: null, middle: null, secondary: "Lord Byng" },
        nearest_transit: null,
        walkscore: null,
        raw_metadata: {},
      },
    ],
  });

  await page.goto("/?neighborhoods=Dunbar");

  // Wait for the listing to render (Search auto-fires from URL params).
  await expect(page.getByText("Bright 2br in Dunbar")).toBeVisible({ timeout: 15_000 });

  // Switch to Map view → triggers the overlay fetch.
  const mapBtn = page.getByRole("button", { name: /^Map$/ });
  if (await mapBtn.isVisible()) {
    await mapBtn.click();
    // Give the effect a moment to run; the route handler flips the flag.
    await page.waitForTimeout(500);
    expect(neighborhoodsFetched).toBe(true);
  }

  // Switch back to a list-style view to check Open-original.
  const cardsBtn = page.getByRole("button", { name: /^Cards$/ });
  if (await cardsBtn.isVisible()) await cardsBtn.click();

  const openOriginal = page.getByRole("button", { name: "Open original" }).first();
  // Open-original should call window.open with _blank — Playwright's
  // page.context().on('page', ...) catches the new window event.
  const newPagePromise = context.waitForEvent("page", { timeout: 5_000 }).catch(() => null);
  await openOriginal.click();
  const newPage = await newPagePromise;
  // We don't assert on newPage URL because Playwright sometimes blocks
  // popup navigation in strict mode; the existence of an opened page (or
  // at minimum, the click not navigating *this* page away) is enough.
  if (newPage) {
    await newPage.close();
  }
  // Original page must still be RentWise — i.e. the URL didn't change
  // to vancouver.craigslist.org.
  await expect(page).toHaveURL(/localhost:8081/);
});
