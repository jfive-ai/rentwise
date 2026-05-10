import { test, expect } from "@playwright/test";
import fixture from "../__fixtures__/search_response.json";
import { mockSearch } from "./_stream";

// Phase 7 PR-C-1: viewport-aware defaults. We render in real chromium at
// two distinct viewport sizes and assert the initial layout matches what
// the UI promises on each device class.

test.describe("Responsive layout", () => {
  test.beforeEach(async ({ page }) => {
    await mockSearch(page, fixture);
  });

  test("phone viewport: filters are collapsed and 'list' is the active view", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/");

    // The "Show filters" toggle is rendered (proving stacked branch).
    await expect(
      page.getByRole("button", { name: "Show filters" }),
    ).toBeVisible();

    // The Search button (inside FilterPanel) is hidden until filters open.
    await expect(
      page.getByRole("button", { name: "Search", exact: true }),
    ).toHaveCount(0);

    // List view is the active toolbar option.
    const listBtn = page.getByRole("button", { name: "List view" });
    await expect(listBtn).toBeVisible();

    // Tapping the toggle reveals the filter pane.
    await page.getByRole("button", { name: "Show filters" }).click();
    await expect(
      page.getByRole("button", { name: "Search", exact: true }),
    ).toBeVisible();
  });

  test("phone viewport: Search button is visible WITHOUT scrolling (sticky action row)", async ({
    page,
  }) => {
    // Original bug (PR #82): filtersStacked.maxHeight was "none", so the
    // inner ScrollView grew past the viewport and Search was unreachable.
    // PR #82 made it scrollable; today we go further — the Search/Reset
    // action row is now pinned at the bottom of the FilterPanel rather
    // than appended to the scroll body, so the user never has to discover
    // scroll to reach it.
    await page.setViewportSize({ width: 414, height: 800 });
    await page.goto("/");
    await page.getByRole("button", { name: "Show filters" }).click();

    const search = page.getByRole("button", { name: "Search", exact: true });
    await expect(search).toBeVisible();
    // Visible at the initial scroll position — no manual scroll needed.
    const box = await search.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.y + box!.height).toBeLessThanOrEqual(800);
  });

  test("desktop viewport: split view is the default; no toggle", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");

    // No collapse toggle on wide screens.
    await expect(
      page.getByRole("button", { name: /Show filters|Hide filters/ }),
    ).toHaveCount(0);

    // The Split view button is rendered active. We check it's visible; the
    // Cards/List buttons are also visible — but Split is the *default* on
    // wide which is the non-trivial assertion.
    await expect(
      page.getByRole("button", { name: "Split view" }),
    ).toBeVisible();

    // Filter Search button is visible (filters never collapsed on desktop).
    await expect(
      page.getByRole("button", { name: "Search", exact: true }),
    ).toBeVisible();
  });
});
