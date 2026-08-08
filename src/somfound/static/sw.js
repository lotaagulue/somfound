// Somfound service worker — deliberately minimal. This is NOT a full offline
// app (no background-sync queue, no caching of dynamic report data — that's
// real scope creep for an MVP). What it does:
//   1. Cache-first for map tiles + the vendored-via-CDN Leaflet assets, since
//      those are the expensive, effectively-static part of loading the map
//      on a slow rural connection.
//   2. Cache-first for our own static assets (style.css, icons).
//   3. A friendly offline fallback page for navigations, instead of the
//      browser's own dead-connection error screen — mentions that an
//      in-progress report is saved locally (see report_form.html's draft
//      autosave) rather than lost.
// API calls (/api/...) and all POSTs are always passed straight through —
// never cached, never intercepted.

const SHELL_CACHE = 'somfound-shell-v1';
const TILE_CACHE = 'somfound-tiles-v1';

const SHELL_ASSETS = [
  '/static/style.css',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/favicon-32.png',
  '/static/icons/apple-touch-icon.png',
];

const OFFLINE_HTML = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Offline — Somfound</title>
<style>
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; background:#faf6f0; color:#1c1f2e; padding:2.5rem 1.5rem; max-width:480px; margin:0 auto; line-height:1.5; }
  h1 { color:#1b2999; }
  a { color:#2638c4; }
</style></head>
<body>
  <h1>You're offline</h1>
  <p>Somfound needs a connection to load live reports or submit new ones.</p>
  <p>Filling out a report? What you typed is saved on this device — reconnect and reopen
     <a href="/report">the report page</a> to pick up where you left off.</p>
  <p><a href="/">Try the map again</a></p>
</body></html>`;

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_ASSETS))
      .catch(() => {}) // e.g. installing while already offline — not fatal
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(
        names
          .filter((name) => name !== SHELL_CACHE && name !== TILE_CACHE)
          .map((name) => caches.delete(name))
      )
    )
  );
  self.clients.claim();
});

function isMapAsset(url) {
  return url.hostname.endsWith('tile.openstreetmap.org') || url.hostname === 'unpkg.com';
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return; // never touch POSTs (report submit, confirm, redeem, moderation actions...)

  const url = new URL(request.url);

  if (isMapAsset(url)) {
    event.respondWith(
      caches.open(TILE_CACHE).then((cache) =>
        cache.match(request).then((cached) => {
          const network = fetch(request)
            .then((response) => {
              // Cross-origin no-cors responses are "opaque" (status 0, not
              // response.ok) but are still legitimately cacheable.
              if (response.ok || response.type === 'opaque') cache.put(request, response.clone());
              return response;
            })
            .catch(() => cached);
          return cached || network;
        })
      )
    );
    return;
  }

  if (url.origin === self.location.origin && url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.open(SHELL_CACHE).then((cache) =>
        cache.match(request).then((cached) => cached || fetch(request).then((response) => {
          cache.put(request, response.clone());
          return response;
        }))
      )
    );
    return;
  }

  if (request.mode === 'navigate') {
    // Content here changes constantly (new reports, moderation decisions) —
    // always prefer the network; only fall back when it's genuinely down.
    event.respondWith(
      fetch(request).catch(() => new Response(OFFLINE_HTML, { headers: { 'Content-Type': 'text/html' } }))
    );
    return;
  }

  // Everything else (API calls, etc.): default browser behavior, no caching.
});
