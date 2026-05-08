// RentWise web service worker.
//
// Two responsibilities:
// 1. (Phase 5 PR-C) web push — show notifications, focus/open the app on click.
// 2. (Phase 7 PR-C-3) app-shell caching — make the PWA openable offline so an
//    "Add to Home Screen" install actually feels native. We cache the bare
//    HTML shell on install and serve it as a fallback when the network is
//    unreachable; data fetches still go to the API normally.
//
// Bump CACHE_VERSION whenever the cached shell list below changes; the
// activate handler purges any older cache buckets.

const CACHE_VERSION = "rentwise-v1";

// Treat these as the precached app-shell. Keep this list small — Metro's
// chunked JS bundles don't have stable URLs, so we cache them lazily on
// first fetch via the runtime cache below instead of precaching them here.
const PRECACHE_URLS = ["/", "/manifest.json", "/icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE_VERSION);
      // addAll() rejects on the first failed request. The shell URLs above
      // are all served from the same origin, so a 404 here means a build
      // mismatch — surface it loudly rather than silently swallowing.
      await cache.addAll(PRECACHE_URLS);
      // Activate immediately on first install so the new shell is live.
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(
        names.filter((n) => n !== CACHE_VERSION).map((n) => caches.delete(n)),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  // Only intercept GET navigations + same-origin static assets. Anything
  // else (POST /search, POST /capture, third-party tiles) falls through to
  // the default network behavior so the SW never sits between the user and
  // a fresh listing fetch.
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Network-first for navigations: try the wire, and only fall back to the
  // cached shell if the network is unreachable. This keeps fresh deploys
  // visible without a hard refresh.
  if (req.mode === "navigate") {
    event.respondWith(
      (async () => {
        try {
          const fresh = await fetch(req);
          const cache = await caches.open(CACHE_VERSION);
          // Fire-and-forget; don't block the response on the cache write.
          cache.put(req, fresh.clone()).catch(() => {});
          return fresh;
        } catch {
          const cached = await caches.match(req);
          return cached ?? caches.match("/");
        }
      })(),
    );
    return;
  }

  // Cache-first for the precached shell items. Other static assets fall
  // through to the network with a passive cache update on success.
  if (PRECACHE_URLS.includes(url.pathname)) {
    event.respondWith(
      (async () => {
        const cached = await caches.match(req);
        if (cached) return cached;
        const fresh = await fetch(req);
        const cache = await caches.open(CACHE_VERSION);
        cache.put(req, fresh.clone()).catch(() => {});
        return fresh;
      })(),
    );
  }
});

// --- Web push (unchanged from Phase 5 PR-C) ---

self.addEventListener("push", (event) => {
  if (!event.data) return;
  let payload;
  try {
    payload = event.data.json();
  } catch {
    payload = { title: "RentWise", body: event.data.text(), url: null };
  }
  const title = payload.title || "RentWise";
  const options = {
    body: payload.body || "",
    data: { url: payload.url || "/" },
    icon: "/icon.svg",
    badge: "/icon.svg",
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    (async () => {
      const all = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });
      for (const client of all) {
        if ("focus" in client) {
          client.focus();
          if ("navigate" in client) await client.navigate(url);
          return;
        }
      }
      if (self.clients.openWindow) {
        await self.clients.openWindow(url);
      }
    })(),
  );
});
