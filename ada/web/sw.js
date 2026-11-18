// Service worker: offline app shell. API calls are never cached here (the app keeps its own
// IndexedDB catalog/outbox), so private data never sits in the HTTP cache.
const VERSION = 'ada-v1.0.0-r2';
const SHELL = [
  '/', '/index.html', '/manifest.webmanifest', '/css/app.css',
  '/js/app.js', '/js/api.js', '/js/dom.js', '/js/i18n.js', '/js/db.js', '/js/sync.js', '/js/scanner.js',
  '/js/receipt.js', '/js/qr.js',
  '/js/views/login.js', '/js/views/pos.js', '/js/views/chat.js', '/js/views/products.js', '/js/views/dashboard.js',
  '/js/views/sales.js', '/js/views/alerts.js', '/js/views/staff.js', '/js/views/settings.js', '/js/views/setup.js',
  '/vendor/qrcode-generator-2.0.4.mjs', '/vendor/zxing-0.23.0.min.js',
  '/icons/icon-192.png', '/icons/icon-512.png', '/icons/favicon.svg',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('message', (e) => { if (e.data === 'skipWaiting') self.skipWaiting(); });

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  if (url.pathname.startsWith('/api/') || url.pathname === '/health') return;   // network only
  // Stale-while-revalidate for the shell: instant load, fresh files next time.
  e.respondWith(caches.open(VERSION).then(async (cache) => {
    const cached = await cache.match(e.request, { ignoreSearch: true });
    const network = fetch(e.request).then((res) => {
      if (res.ok && res.type === 'basic') cache.put(e.request, res.clone());
      return res;
    }).catch(() => cached || cache.match('/index.html'));
    return cached || network;
  }));
});
