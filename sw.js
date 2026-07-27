// v25 adds personal verdict notifications for installed PWAs.
const CACHE_VERSION = 'checker-pwa-v25-push-notifications';
const STATIC_CACHE  = `${CACHE_VERSION}-static`;
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`;

// Ресурсы, которые кэшируем сразу при установке SW
const PRECACHE_URLS = [
  '/manifest.json',
  '/static/pwa/icon-192.png',
  '/static/pwa/icon-512.png',
  '/static/pwa/apple-touch-icon-180.png',
  '/static/vendor/tailwind-cdn.js',
  '/static/vendor/google-sans.css',
  '/static/css/page-transitions.css?v=20260601-3',
  '/static/js/page-transitions.js?v=20260728-1',
  '/static/js/push-notifications.js?v=20260728-1',
  '/static/vendor/fonts/google-sans-cyrillic-700.woff2',
  '/static/vendor/fonts/google-sans-cyrillic-ext-700.woff2',
  '/static/vendor/fonts/google-sans-latin-700.woff2',
  '/static/vendor/fonts/google-sans-latin-ext-700.woff2',
  '/static/telegram.svg',
  '/static/home.svg',
  '/static/home_active.svg',
  '/static/verdicts.svg',
  '/static/verdicts_active.svg',
  '/static/balance.svg',
  '/static/start_prov.png',
  '/static/find_brend.png',
  '/static/avatar-placeholder.png',
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

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

self.addEventListener('push', (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (_) {
    payload = {
      title: 'Checker',
      body: event.data ? event.data.text() : 'Статус проверки обновлён',
    };
  }

  const title = payload.title || 'Checker';
  const options = {
    body: payload.body || 'Статус проверки обновлён',
    icon: '/static/pwa/icon-192.png',
    badge: '/static/pwa/icon-192.png',
    tag: payload.tag || 'checker-notification',
    renotify: true,
    data: {
      url: payload.url || '/verdicts/',
      peer_id: payload.peer_id || null,
      message_id: payload.message_id || null,
    },
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const targetUrl = new URL(event.notification.data?.url || '/verdicts/', self.location.origin).href;

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clients) => {
        for (const client of clients) {
          const clientUrl = new URL(client.url);
          if (clientUrl.origin === self.location.origin) {
            return client.navigate(targetUrl).then((navigatedClient) => (navigatedClient || client).focus());
          }
        }
        return self.clients.openWindow(targetUrl);
      })
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
  const response = await fetch(new Request(request, {
    cache: 'no-store',
    credentials: 'same-origin',
  }));
  const contentType = (response.headers.get('content-type') || '').toLowerCase();
  const expectedType = expectedStaticContentType(new URL(request.url).pathname);
  if (response.ok && !response.redirected && (!expectedType || contentType.startsWith(expectedType))) {
    const cache = await caches.open(STATIC_CACHE);
    cache.put(request, response.clone());
  }
  return response;
}

function expectedStaticContentType(pathname) {
  if (/\.(png|jpe?g|webp|gif|avif)$/i.test(pathname)) return 'image/';
  if (/\.svg$/i.test(pathname)) return 'image/svg+xml';
  if (/\.css$/i.test(pathname)) return 'text/css';
  if (/\.js$/i.test(pathname)) return 'application/javascript';
  if (/\.(woff2?|ttf|otf)$/i.test(pathname)) return 'font/';
  return null;
}

// Network-first: HTML-страницы (нужна свежесть, фолбэк на кэш)
async function networkFirst(request) {
  const cacheKey = getCacheKey(request);
  const cache = await caches.open(RUNTIME_CACHE);
  try {
    const response = await fetch(new Request(request, { cache: 'no-store' }));
    if (response.ok) {
      cache.put(cacheKey, response.clone());
    }
    return response;
  } catch (_) {
    const cached = await caches.match(cacheKey);
    if (cached) return cached;
    // Офлайн-заглушка для навигации
    const offlinePage = await caches.match('/');
    return offlinePage || new Response('Offline', { status: 503 });
  }
}

function getCacheKey(request) {
  const url = new URL(request.url);
  if (url.searchParams.has('__spa_fetch')) {
    url.searchParams.delete('__spa_fetch');
    return url.href;
  }
  return request;
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

// ─── Fetch: роутинг ───────────────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const { request } = event;

  if (request.method !== 'GET') return;
  const url = new URL(request.url);

  // Все остальные кросс-доменные запросы — не перехватываем
  if (url.origin !== self.location.origin) return;

  // Не кэшируем admin, API-запросы и webhook
  if (
    url.pathname.startsWith('/admin/') ||
    url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/vkchat/api/') ||
    url.pathname.includes('webhook')
  ) {
    return;
  }

  // Сам service worker всегда должен идти из сети, иначе PWA залипает на старой версии.
  if (url.pathname === '/sw.js') {
    return;
  }

  // Статические файлы → cache-first
  if (
    url.pathname.startsWith('/static/') ||
    url.pathname.startsWith('/media/')  ||
    url.pathname === '/manifest.json'
  ) {
    event.respondWith(cacheFirst(request));
    return;
  }

  const accept = request.headers.get('accept') || '';

  // HTML-навигация и SPA-fetch страниц → network-first
  if (request.mode === 'navigate' || accept.includes('text/html')) {
    event.respondWith(networkFirst(request));
    return;
  }

  // Остальное → stale-while-revalidate
  event.respondWith(staleWhileRevalidate(request));
});
