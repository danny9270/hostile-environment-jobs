// Service worker for the job alerts app (/app/). It only shows push notifications and opens the job when one is tapped;
// pages aren't cached, so the site always shows the latest listings.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", event => event.waitUntil(self.clients.claim()));

self.addEventListener("push", event => {
  let n = {};
  try { n = event.data ? event.data.json() : {}; } catch { n = { body: event.data && event.data.text() }; }
  event.waitUntil(self.registration.showNotification(n.title || "New job on Hostile Environment Jobs", {
    body: n.body || "", tag: n.tag, icon: "/icon-192.png", badge: "/favicon-96x96.png", data: { url: n.url || "/app/#matches" },
  }));
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/app/", self.location.origin).href;
  event.waitUntil((async () => {
    const open = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of open) {
      if ("navigate" in c) { await c.focus(); return c.navigate(url); }
    }
    return self.clients.openWindow(url);
  })());
});
