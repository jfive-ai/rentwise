/**
 * Phase 7 PR-C-3: PWA install support.
 *
 * Expo's web export emits a single index.html and bundles JS via Metro, so
 * the simplest reliable way to attach <link rel="manifest"> and <meta
 * name="theme-color"> is at runtime when the layout first mounts. We also
 * register the service worker here unconditionally — browsers gate "Add to
 * Home Screen" on having both a manifest and an active SW.
 *
 * Each step is idempotent so a hot reload doesn't stack duplicate elements
 * or registrations.
 */

const THEME_COLOR = "#0f172a";

/** True if running in a real browser (jsdom passes too — that's intentional for tests). */
function isBrowser(): boolean {
  return typeof document !== "undefined";
}

function ensureLink(rel: string, href: string): void {
  if (!isBrowser()) return;
  const existing = document.querySelector(`link[rel="${rel}"]`);
  if (existing) {
    existing.setAttribute("href", href);
    return;
  }
  const link = document.createElement("link");
  link.setAttribute("rel", rel);
  link.setAttribute("href", href);
  document.head.appendChild(link);
}

function ensureMeta(name: string, content: string): void {
  if (!isBrowser()) return;
  const existing = document.querySelector(`meta[name="${name}"]`);
  if (existing) {
    existing.setAttribute("content", content);
    return;
  }
  const meta = document.createElement("meta");
  meta.setAttribute("name", name);
  meta.setAttribute("content", content);
  document.head.appendChild(meta);
}

/** Register /sw.js once. Idempotent — repeat calls are no-ops. */
export async function registerServiceWorker(): Promise<void> {
  if (!isBrowser()) return;
  if (!("serviceWorker" in navigator)) return;
  try {
    // The browser dedupes registrations by scriptURL + scope, so calling
    // register("/sw.js") twice is fine. We swallow errors on purpose: SW
    // registration failures shouldn't crash the app.
    await navigator.serviceWorker.register("/sw.js");
  } catch {
    /* ignore — PWA is a progressive enhancement */
  }
}

/** Wire up everything PWA-related. Safe to call from a useEffect. */
export function installPwaHooks(): void {
  ensureLink("manifest", "/manifest.json");
  ensureLink("icon", "/icon.svg");
  ensureMeta("theme-color", THEME_COLOR);
  void registerServiceWorker();
}
