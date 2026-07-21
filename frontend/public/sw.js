/* Finance-Alert service worker — NETWORK-FIRST.
 *
 * Deliberately network-first: it always tries the network and only falls back
 * to cache when OFFLINE. This makes the app installable + usable offline
 * WITHOUT the classic stale-hashed-bundle trap — when online, a fresh deploy is
 * always served immediately. It never touches /api (dynamic + authed).
 */
const CACHE = "fa-runtime-v1";

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  // Only same-origin, non-API GETs. Everything else uses the default handling.
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  event.respondWith(
    fetch(req)
      .then((res) => {
        // Cache successful navigations + hashed static assets for offline use.
        if (res.ok && (req.mode === "navigate" || url.pathname.startsWith("/assets/"))) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      })
      .catch(() =>
        caches.match(req).then((cached) => {
          if (cached) return cached;
          // Offline SPA fallback: serve the app shell for navigations.
          return req.mode === "navigate" ? caches.match("/") : Response.error();
        }),
      ),
  );
});
