import { test, expect } from "@playwright/test";
import fixture from "../__fixtures__/search_response.json";
import { mockSearch } from "./_stream";

test.describe("URL filter persistence (Phase 7 PR-C-2)", () => {
  test.beforeEach(async ({ page }) => {
    await mockSearch(page, fixture);
  });

  test("landing on /?bedrooms_min=2&price_max=3000 hydrates filters and auto-runs the search", async ({
    page,
  }) => {
    // Pin a desktop viewport so PR-C-1's filter pane is open by default.
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto("/?bedrooms_min=2&price_max=3000");

    // Search auto-fires from the URL — count appears without clicking Search.
    await expect(page.getByText("5 listings", { exact: true })).toBeVisible();

    // The bedrooms-2 chip is in its selected state. We can't easily probe
    // styling, so instead verify the price input came back filled.
    await expect(page.getByPlaceholder("Max")).toHaveValue("3000");
  });

  test("clicking Search after typing filters writes them into the URL", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto("/");

    await page.getByRole("button", { name: "2", exact: true }).click();
    await page.getByPlaceholder("Max").fill("3000");
    await page.getByRole("button", { name: "Search", exact: true }).click();

    await expect(page.getByText("5 listings", { exact: true })).toBeVisible();

    // The URL now carries the encoded filter so the page is shareable.
    await expect.poll(() => new URL(page.url()).searchParams.get("bedrooms_min")).toBe("2");
    expect(new URL(page.url()).searchParams.get("price_max")).toBe("3000");
  });
});
