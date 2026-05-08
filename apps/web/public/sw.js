// RentWise web push service worker (Phase 5 PR-C).
//
// The backend's WebPushNotifier sends a JSON payload of the shape:
//   { title: string, body: string, url: string | null }
//
// We surface it as a notification and, on click, focus an existing
// RentWise tab if one is open or open a new one to `url` (which the
// backend builds as `<app_base_url>/?saved=<cache_key>`).

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
    icon: "/favicon.ico",
    badge: "/favicon.ico",
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
