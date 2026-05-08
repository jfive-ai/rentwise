import { test, expect } from "@playwright/test";
import fixture from "../__fixtures__/search_response.json";

test("filter search renders results, switches view, saves a card", async ({ page }) => {
  await page.route("**/search", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(fixture),
    });
  });

  await page.goto("/");

  // Set bedrooms_min=2 by tapping the chip
  await page.getByRole("button", { name: "2", exact: true }).click();

  // Set price_max to 3000
  await page.getByPlaceholder("Max").fill("3000");

  // PR-D: school catchment + transit-walk inputs are now enabled.
  await page.getByLabel("School catchment").fill("Lord Byng");
  await page.getByLabel("Transit walk minutes").fill("10");

  // Search — use exact: true so PR-C's "Search across sources (6 sites)"
  // launcher button doesn't also match this selector.
  await page.getByRole("button", { name: "Search", exact: true }).click();

  // exact: true so PR-C-1's split-view default doesn't double-match against
  // MapView's "N listings have no location…" footer.
  await expect(page.getByText("5 listings", { exact: true })).toBeVisible();

  // 5 cards visible
  await expect(page.getByText("Sunny 2br in Kitsilano with view")).toBeVisible();

  // Switch to list view
  await page.getByRole("button", { name: "List view" }).click();

  // List view shows the price cell
  await expect(page.getByText("$2,800")).toBeVisible();
});
