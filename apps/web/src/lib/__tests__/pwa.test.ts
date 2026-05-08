/** @jest-environment jsdom */
import manifest from "../../../public/manifest.json";
import { installPwaHooks, registerServiceWorker } from "@/src/lib/pwa";

describe("manifest.json", () => {
  it("declares the four fields browsers gate the install prompt on", () => {
    expect(manifest.name).toBeTruthy();
    expect(manifest.short_name).toBeTruthy();
    expect(manifest.start_url).toBe("/");
    expect(manifest.display).toBe("standalone");
  });

  it("ships an icon (any size + 'maskable' purpose so iOS Home Screen looks right)", () => {
    expect(Array.isArray(manifest.icons)).toBe(true);
    expect(manifest.icons.length).toBeGreaterThan(0);
    const purposes = manifest.icons.flatMap((i) => i.purpose.split(/\s+/));
    expect(purposes).toContain("maskable");
  });
});

describe("installPwaHooks", () => {
  beforeEach(() => {
    document.head.innerHTML = "";
  });

  it("adds <link rel=manifest>, <link rel=icon>, and <meta name=theme-color> on first call", () => {
    installPwaHooks();
    expect(document.querySelector('link[rel="manifest"]')?.getAttribute("href")).toBe(
      "/manifest.json",
    );
    expect(document.querySelector('link[rel="icon"]')?.getAttribute("href")).toBe(
      "/icon.svg",
    );
    expect(
      document.querySelector('meta[name="theme-color"]')?.getAttribute("content"),
    ).toBe("#0f172a");
  });

  it("is idempotent: calling twice doesn't duplicate elements", () => {
    installPwaHooks();
    installPwaHooks();
    expect(document.querySelectorAll('link[rel="manifest"]')).toHaveLength(1);
    expect(document.querySelectorAll('link[rel="icon"]')).toHaveLength(1);
    expect(document.querySelectorAll('meta[name="theme-color"]')).toHaveLength(1);
  });
});

describe("registerServiceWorker", () => {
  it("calls navigator.serviceWorker.register with /sw.js when SW is supported", async () => {
    const register = jest.fn().mockResolvedValue({});
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { register },
    });
    await registerServiceWorker();
    expect(register).toHaveBeenCalledWith("/sw.js");
  });

  it("swallows registration errors — PWA is progressive", async () => {
    const register = jest.fn().mockRejectedValue(new Error("nope"));
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { register },
    });
    await expect(registerServiceWorker()).resolves.toBeUndefined();
  });

  it("is a no-op when serviceWorker is unavailable", async () => {
    // @ts-expect-error — deleting an optional API on the mocked navigator
    delete navigator.serviceWorker;
    await expect(registerServiceWorker()).resolves.toBeUndefined();
  });
});
