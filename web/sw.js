// Offline support: the app files are cached on first visit. Bump VERSION
// whenever any of them changes so phones pick up the new files.
const VERSION = 'fx9860-v1';
const FILES = [
  './', 'index.html', 'app.js', 'fxweb.wasm', 'skin@3x.png', 'layout.json',
  'manifest.webmanifest', 'icon-180.png', 'icon-192.png', 'icon-512.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  e.respondWith(caches.match(e.request, { ignoreSearch: true }).then((hit) => hit || fetch(e.request)));
});
