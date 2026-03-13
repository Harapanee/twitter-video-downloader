// Service Worker: serves cached blobs with Content-Disposition for iOS Safari Files app saving
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/sw-download/')) {
    event.respondWith(
      caches.open('sw-downloads').then(async (cache) => {
        const resp = await cache.match(event.request.url);
        if (resp) {
          cache.delete(event.request.url);
          return resp;
        }
        return new Response('Download not found', { status: 404 });
      })
    );
  }
});
