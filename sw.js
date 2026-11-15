// Service worker for the job alerts app (/app/). It only shows push notifications and opens the job when one is tapped;
// The app and deployment guide pages are fetched fresh each time, with the last copy kept for when there's no signal.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", event => event.waitUntil(self.clients.claim()));

const OFFLINE = "hej-offline-v1";
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin || !["/app/", "/deploy/"].includes(url.pathname)) return;
  event.respondWith(fetch(event.request).then(res => {
    if (res.ok) { const copy = res.clone(); caches.open(OFFLINE).then(c => c.put(url.pathname, copy)); }
    return res;
  }).catch(() => caches.match(url.pathname).then(hit => hit || Response.error())));
});

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
