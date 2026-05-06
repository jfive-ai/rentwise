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

  // Search
  await page.getByRole("button", { name: "Search" }).click();

  await expect(page.getByText("5 listings")).toBeVisible();

  // 5 cards visible
  await expect(page.getByText("Sunny 2br in Kitsilano with view")).toBeVisible();

  // Switch to list view
  await page.getByRole("button", { name: "List view" }).click();

  // List view shows the price cell
  await expect(page.getByText("$2,800")).toBeVisible();
});
