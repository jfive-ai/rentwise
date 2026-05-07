import { test, expect } from "@playwright/test";

test("first-run wizard: 404 → wizard → save → search reachable", async ({ page }) => {
  // Clear localStorage flag
  await page.addInitScript(() => {
    window.localStorage.removeItem("rentwise.wizardCompleted");
  });

  // Stub backend
  await page.route("**/settings/llm", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "no_llm_settings" }),
      });
    } else {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          primary_model: "openrouter/qwen/qwen-2.5-72b-instruct:free",
          primary_api_key_masked: "sk-or-...test",
          fallback_model: null,
          fallback_api_key_masked: null,
          custom_base_url: null,
          timeout_seconds: 30,
        }),
      });
    }
  });
  await page.route("**/settings/llm/test", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        error: null,
        latency_ms: 50,
        model_used: "m",
      }),
    });
  });

  await page.goto("/");

  // Wizard appears
  await expect(page.getByText(/Welcome to RentWise/i)).toBeVisible();

  // Fill API key, test, finish
  await page.getByLabel("API key").fill("sk-or-test");
  await page.getByRole("button", { name: "Test connection" }).click();
  await expect(page.getByText(/Connection ok/i)).toBeVisible();
  await page.getByRole("button", { name: "Finish" }).click();

  // Now on the normal app — match exactly to disambiguate from the
  // PR-C "Search across sources" launcher button.
  await expect(
    page.getByRole("button", { name: "Search", exact: true }),
  ).toBeVisible({ timeout: 10000 });
});
