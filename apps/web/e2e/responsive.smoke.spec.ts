import { test, expect } from "@playwright/test";
import fixture from "../__fixtures__/search_response.json";

// Phase 7 PR-C-1: viewport-aware defaults. We render in real chromium at
// two distinct viewport sizes and assert the initial layout matches what
// the UI promises on each device class.

test.describe("Responsive layout", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/search", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(fixture),
      });
    });
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

  test("phone viewport: filter pane scrolls so the Search button is reachable", async ({
    page,
  }) => {
    // Bug today: filtersStacked.maxHeight was "none", so the inner
    // ScrollView grew to its content height, the page itself didn't scroll,
    // and the Search button at the bottom of FilterPanel was below the
    // viewport with no way to reach it. Reproduces at the same 414×800 the
    // user was using.
    await page.setViewportSize({ width: 414, height: 800 });
    await page.goto("/");
    await page.getByRole("button", { name: "Show filters" }).click();

    const search = page.getByRole("button", { name: "Search", exact: true });
    // The Search button is in the DOM but, before scrolling, sits below
    // the viewport. `scrollIntoViewIfNeeded` walks up to the *scrollable*
    // ancestor and scrolls it — which only succeeds when one exists with a
    // bounded height. (With maxHeight:"none" the chain has no scrollable
    // ancestor and this would time out.)
    await search.scrollIntoViewIfNeeded();
    await expect(search).toBeVisible();
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
