/* Service Worker: iOS Safari download helper
   Intercepts navigation to /__download/* and serves cached blobs
   with Content-Disposition: attachment so files save to the Files app. */

const DOWNLOAD_CACHE = 'ios-download-v1';

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/__download/')) {
    event.respondWith(handleDownload(url));
  }
});

async function handleDownload(url) {
  const cache = await caches.open(DOWNLOAD_CACHE);
  const cached = await cache.match(url.href);
  if (cached) {
    await cache.delete(url.href);
    return cached;
  }
  return new Response('Download not found', { status: 404 });
}
