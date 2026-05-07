import { test, expect } from "@playwright/test";
import SEARCH_FIXTURE from "../__fixtures__/search_response.json";

test("NL flow: type → parse → chips → search", async ({ page }) => {
  await page.route("**/translate-query", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        query: {
          neighborhoods: ["Kitsilano"],
          pets: "any",
          furnished: "any",
          free_text_keywords: [],
          bedrooms_min: 2,
          price_max: 3000,
        },
        unsupported_filters: [],
        lang_detected: "en",
        model_used: "openrouter/qwen/qwen-2.5-72b-instruct:free",
      }),
    });
  });
  await page.route("**/search", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(SEARCH_FIXTURE),
    });
  });

  await page.goto("/");

  // Switch to NL mode
  await page.getByRole("button", { name: "Natural language" }).click();
  await page.getByLabel("Search input").fill("2 bedroom in Kitsilano under 3000");
  await page.getByRole("button", { name: "Parse" }).click();

  // Chips appear (target the remove buttons since text may also appear in the textarea)
  await expect(page.getByRole("button", { name: "Remove Kitsilano" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Remove ≤$3000" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Remove 2+ beds" })).toBeVisible();

  // Search
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByText("5 listings")).toBeVisible();
});
