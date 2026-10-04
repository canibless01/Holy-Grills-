/* ==========================================================================
   Holy Grill — Service Worker
   --------------------------------------------------------------------------
   Caching strategies:
     • Navigation (HTML)        → network-first, cache + offline fallback
     • App shell + icons        → cache-first, version-busted on install
     • Images & fonts           → stale-while-revalidate
     • Source modules, JS, CSS, API → NEVER cached, handled by the network

   That last line is the important one. Bundle and source files must never be
   served from cache: their contents change between builds while their URLs may
   not, so a cached copy can pair a stale React with a fresh react-dom and crash
   the app on load. Only versioned, content-addressed or truly static files are
   cached here.
   ========================================================================== */

// OneSignal push support — harmless if OneSignal isn't configured.
try { importScripts('https://cdn.onesignal.com/sdks/OneSignalSDKWorker.js'); } catch (e) { /* no-op */ }

// Bumping the version makes the activate handler purge every older cache.
const CACHE_VERSION = 'hg-v2';
const SHELL_CACHE = `${CACHE_VERSION}-shell`;
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`;
const OFFLINE_URL = '/offline.html';

const SHELL_ASSETS = [
  '/',
  '/index.html',
  '/offline.html',
  '/manifest.json',
  '/icons/icon.svg',
  '/icons/maskable.svg',
];

// Anything that must always come from the network, never from a cache: dev
// server modules, Vite internals, and every JS/CSS/component file.
const neverCache = (pathname) =>
  pathname.startsWith('/src/') ||
  pathname.startsWith('/node_modules/') ||
  pathname.startsWith('/@vite') ||
  pathname.startsWith('/@react-refresh') ||
  pathname.startsWith('/@id/') ||
  pathname.startsWith('/@fs/') ||
  pathname.endsWith('.js') ||
  pathname.endsWith('.mjs') ||
  pathname.endsWith('.jsx') ||
  pathname.endsWith('.ts') ||
  pathname.endsWith('.tsx') ||
  pathname.endsWith('.css');

// --- Install: pre-cache the app shell ---
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_ASSETS)).catch(() => {})
  );
  self.skipWaiting();
});

// --- Activate: clear every cache from an older version ---
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== SHELL_CACHE && k !== RUNTIME_CACHE)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// --- Message handler: update flow ---
self.addEventListener('message', (event) => {
  if (event.data === 'SKIP_WAITING') self.skipWaiting();
});

// --- Fetch: routing by request type ---
self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  // Skip cross-origin + OneSignal/SDK requests.
  if (url.origin !== self.location.origin) return;
  if (url.pathname.includes('OneSignalSDK')) return;

  // Source modules, bundles, styles, Vite internals → straight to the network.
  if (neverCache(url.pathname)) return;

  // Navigation → network-first, offline fallback.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((res) => {
          const copy = res.clone();
          caches.open(SHELL_CACHE).then((c) => c.put(request, copy));
          return res;
        })
        .catch(() =>
          caches.match(request).then((cached) => cached || caches.match(OFFLINE_URL))
        )
    );
    return;
  }

  // Static shell assets → cache-first.
  if (SHELL_ASSETS.includes(url.pathname) || url.pathname.startsWith('/icons/')) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((res) => {
        const copy = res.clone();
        caches.open(SHELL_CACHE).then((c) => c.put(request, copy));
        return res;
      }))
    );
    return;
  }

  // Only images and fonts get the runtime cache — never API responses.
  if (request.destination !== 'image' && request.destination !== 'font') return;

  event.respondWith(
    caches.open(RUNTIME_CACHE).then((cache) =>
      cache.match(request).then((cached) => {
        const network = fetch(request)
          .then((res) => {
            if (res && res.status === 200) {
              const copy = res.clone();
              cache.put(request, copy);
            }
            return res;
          })
          .catch(() => cached);
        return cached || network;
      })
    )
  );
});