import { test, expect } from "@playwright/test";
import fixture from "../__fixtures__/search_response.json";

test.describe("PWA install support (Phase 7 PR-C-3)", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/search", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(fixture),
      });
    });
  });

  test("/manifest.json is served and declares standalone display", async ({
    request,
  }) => {
    const res = await request.get("/manifest.json");
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.name).toBe("RentWise");
    expect(body.start_url).toBe("/");
    expect(body.display).toBe("standalone");
    expect(Array.isArray(body.icons)).toBe(true);
    expect(body.icons.length).toBeGreaterThan(0);
  });

  test("/icon.svg is served as image/svg+xml", async ({ request }) => {
    const res = await request.get("/icon.svg");
    expect(res.status()).toBe(200);
    expect(res.headers()["content-type"] ?? "").toContain("image/svg");
  });

  test("home page injects <link rel=manifest> and registers the service worker", async ({
    page,
  }) => {
    await page.goto("/");
    // Wait until our PWA hook injects the link tag.
    await expect(page.locator('link[rel="manifest"]')).toHaveAttribute(
      "href",
      "/manifest.json",
    );
    await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute(
      "content",
      "#0f172a",
    );
    // Service worker registers eagerly. Wait for it to become ready (or
    // surface that the API isn't even there, which would be a real bug).
    const swReady = await page.evaluate(async () => {
      if (!("serviceWorker" in navigator)) return "unsupported";
      const reg = await navigator.serviceWorker.ready;
      return reg.active?.scriptURL ?? "no-active-worker";
    });
    expect(swReady).toContain("/sw.js");
  });
});
