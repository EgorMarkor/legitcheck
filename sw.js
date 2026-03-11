const CACHE_VERSION = 'checker-pwa-v4';
const STATIC_CACHE  = `${CACHE_VERSION}-static`;
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`;

// Ресурсы, которые кэшируем сразу при установке SW
const PRECACHE_URLS = [
  '/',
  '/home/',
  '/manifest.json',
  '/static/pwa/icon-192.png',
  '/static/pwa/icon-512.png',
  '/static/pwa/apple-touch-icon-180.png',
  '/static/pwa/transitions.js',
  '/static/telegram.svg',
  '/static/home.svg',
  '/static/home_active.svg',
  '/static/verdicts.svg',
  '/static/verdicts_active.svg',
  '/static/balance.svg',
  '/static/start_prov.png',
  '/static/find_brend.png',
  '/static/avatar.png',
];

// ─── Install: прекэш ──────────────────────────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => {
        // addAll прерывается при первой ошибке — используем Promise.allSettled
        return Promise.allSettled(
          PRECACHE_URLS.map((url) => cache.add(url).catch(() => null))
        );
      })
      .then(() => self.skipWaiting())
  );
});

// ─── Activate: удаляем старые кэши ───────────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key !== STATIC_CACHE && key !== RUNTIME_CACHE)
            .map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

// ─── Стратегии кэширования ────────────────────────────────────────────────────

// Cache-first: статика (файлы меняются редко, версионируются)
async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) {
    const cache = await caches.open(STATIC_CACHE);
    cache.put(request, response.clone());
  }
  return response;
}

// Network-first: HTML-страницы (нужна свежесть, фолбэк на кэш)
async function networkFirst(request) {
  const cache = await caches.open(RUNTIME_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (_) {
    const cached = await caches.match(request);
    if (cached) return cached;
    // Офлайн-заглушка для навигации
    const offlinePage = await caches.match('/');
    return offlinePage || new Response('Offline', { status: 503 });
  }
}

// Stale-while-revalidate: API-запросы и медиа
async function staleWhileRevalidate(request) {
  const cache  = await caches.open(RUNTIME_CACHE);
  const cached = await cache.match(request);

  const fetchPromise = fetch(request).then((response) => {
    if (response.ok) cache.put(request, response.clone());
    return response;
  }).catch(() => null);

  return cached || (await fetchPromise) || fetch(request);
}

// Внешние CDN: кэшируем через stale-while-revalidate
const CDN_ORIGINS = [
  'https://cdn.tailwindcss.com',
  'https://fonts.googleapis.com',
  'https://fonts.gstatic.com',
  'https://cdn.jsdelivr.net',
];

// ─── Fetch: роутинг ───────────────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const { request } = event;

  if (request.method !== 'GET') return;
  const url = new URL(request.url);

  // Внешние CDN → stale-while-revalidate
  if (CDN_ORIGINS.some((o) => request.url.startsWith(o))) {
    event.respondWith(staleWhileRevalidate(request));
    return;
  }

  // Все остальные кросс-доменные запросы — не перехватываем
  if (url.origin !== self.location.origin) return;

  // Не кэшируем admin, API-запросы и webhook
  if (
    url.pathname.startsWith('/admin/') ||
    url.pathname.startsWith('/api/') ||
    url.pathname.includes('webhook')
  ) {
    return;
  }

  // Статические файлы → cache-first
  if (
    url.pathname.startsWith('/static/') ||
    url.pathname.startsWith('/media/')  ||
    url.pathname === '/manifest.json'   ||
    url.pathname === '/sw.js'
  ) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // HTML-навигация → network-first
  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request));
    return;
  }

  // Остальное → stale-while-revalidate
  event.respondWith(staleWhileRevalidate(request));
});
