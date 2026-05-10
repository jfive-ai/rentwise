import { test, expect } from "@playwright/test";
import SEARCH_FIXTURE from "../__fixtures__/search_response.json";
import { mockSearch } from "./_stream";

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
        model_used: "openrouter/qwen/qwen3-next-80b-a3b-instruct:free",
      }),
    });
  });
  await mockSearch(page, SEARCH_FIXTURE);

  await page.goto("/");

  // Switch to NL mode
  await page.getByRole("button", { name: "Natural language" }).click();
  await page.getByLabel("Search input").fill("2 bedroom in Kitsilano under 3000");
  await page.getByRole("button", { name: "Parse" }).click();

  // Chips appear (target the remove buttons since text may also appear in the textarea)
  await expect(page.getByRole("button", { name: "Remove Kitsilano" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Remove ≤$3000" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Remove 2+ beds" })).toBeVisible();

  // Search — exact:true so Phase 5 PR-A's "Open saved searches" button
  // doesn't also match this selector by name-substring.
  await page.getByRole("button", { name: "Search", exact: true }).click();
  // exact: true so PR-C-1's split-view default doesn't double-match against
  // MapView's "N listings have no location…" footer.
  await expect(page.getByText("5 listings", { exact: true })).toBeVisible();
});

test("NL flow: '3 bedroom in dunbar' parses to chips and searches", async ({
  page,
}) => {
  // Mirrors the actual GPT-5 nano response for this exact phrase: it pins
  // bedrooms_min AND bedrooms_max both to 3 (interprets "3 bedroom" as
  // exactly 3, not 3+), so the chip set is "3+ beds", "≤3 beds", "Dunbar".
  await page.route("**/translate-query", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        query: {
          neighborhoods: ["Dunbar"],
          pets: "any",
          furnished: "any",
          free_text_keywords: [],
          bedrooms_min: 3,
          bedrooms_max: 3,
        },
        unsupported_filters: [],
        lang_detected: "en",
        model_used: "openai/gpt-5-nano",
      }),
    });
  });
  await mockSearch(page, { ...SEARCH_FIXTURE, total: 0, listings: [] });

  await page.goto("/");
  await page.getByRole("button", { name: "Natural language" }).click();
  await page.getByLabel("Search input").fill("3 bedroom in dunbar");
  await page.getByRole("button", { name: "Parse" }).click();

  await expect(page.getByRole("button", { name: "Remove 3+ beds" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Remove ≤3 beds" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Remove Dunbar" })).toBeVisible();

  // Search runs; URL persists the parsed filters (Phase 7 PR-C-2 contract).
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page).toHaveURL(/bedrooms_min=3/);
  await expect(page).toHaveURL(/neighborhoods=Dunbar/);
  await expect(page.getByText("0 listings", { exact: true })).toBeVisible();
});

test("NL flow: 5xx surfaces real server error inline (no silent mode flip)", async ({
  page,
}) => {
  // Regression for the bug we shipped today: NLSearchBar used to swallow
  // 5xx with a generic "LLM unavailable — switched to filter mode" and
  // auto-flip the tab. Both the auto-flip and the masked message hid the
  // real cause (e.g. "OpenRouter 401: No cookie auth credentials found").
  await page.route("**/translate-query", async (route) => {
    await route.fulfill({
      status: 502,
      contentType: "application/json",
      body: JSON.stringify({
        detail: {
          error: "llm_transport_error",
          message:
            "All LLM providers failed; last error: OpenRouter 401 No cookie auth credentials",
        },
      }),
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Natural language" }).click();
  await page.getByLabel("Search input").fill("3 bedroom in dunbar");
  await page.getByRole("button", { name: "Parse" }).click();

  // The actual server message bubbles up in the alert.
  await expect(
    page.getByText(/All LLM providers failed/, { exact: false })
  ).toBeVisible();

  // The user stays in NL mode — the input box is still visible.
  await expect(page.getByLabel("Search input")).toBeVisible();

  // And a recovery action is offered.
  await expect(
    page.getByRole("button", { name: "Use filter mode" })
  ).toBeVisible();
});

test("NL flow: 'Use filter mode' recovery flips to filters and clears the error", async ({
  page,
}) => {
  await page.route("**/translate-query", async (route) => {
    await route.fulfill({
      status: 502,
      contentType: "application/json",
      body: JSON.stringify({
        detail: {
          error: "llm_transport_error",
          message: "LLM down for maintenance",
        },
      }),
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Natural language" }).click();
  await page.getByLabel("Search input").fill("3 bedroom in dunbar");
  await page.getByRole("button", { name: "Parse" }).click();

  await expect(page.getByText("LLM down for maintenance")).toBeVisible();

  await page.getByRole("button", { name: "Use filter mode" }).click();

  // Filter UI's bedroom buttons appear (they only render in filter mode).
  await expect(page.getByRole("button", { name: "Studio" })).toBeVisible();
  // And the inline error is gone.
  await expect(page.getByText("LLM down for maintenance")).toBeHidden();
});
