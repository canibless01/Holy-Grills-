import ReactDOM from 'react-dom/client'
import App from '@/App'
import { isHydratingPrerender } from '@/lib/hydrationMode'
import '@/index.css'

// Track B: pre-rendered routes ship real HTML inside #root (scripts/prerender.mjs),
// so hydrate that markup instead of discarding it.
//
// The pre-render stamps the route it rendered on the container
// (PRERENDER_STAMP_ATTR, see src/lib/hydrationMode.ts). Hydrate only when the
// stamp matches what the browser asked for: if a host ever serves the wrong
// pre-rendered file (stale deploy, SPA fallback), hydrating blind would run
// React against markup from another page, so we drop it and mount fresh — the
// exact behaviour the app had before pre-rendering existed.
const container = document.getElementById('root')

if (container && isHydratingPrerender()) {
  ReactDOM.hydrateRoot(container, <App />)
} else if (container) {
  container.innerHTML = ''
  ReactDOM.createRoot(container).render(<App />)
}

// --- Service Worker registration (PWA) ---
// PRODUCTION ONLY.
//
// The dev server serves source modules and re-optimised dependency chunks whose
// URLs change on every rebuild. A cache-serving worker in that environment
// hands the app a stale React bundle alongside a freshly built react-dom, which
// surfaces as "Cannot read properties of null (reading 'useState')" inside the
// root providers. So in development we never register — and we actively tear
// down any worker and cache left behind by an earlier session.
if ('serviceWorker' in navigator) {
  if (import.meta.env.DEV) {
    navigator.serviceWorker
      .getRegistrations()
      .then((regs) => Promise.all(regs.map((r) => r.unregister())))
      .then(() => (typeof caches !== 'undefined' ? caches.keys() : []))
      .then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
      .catch(() => { /* nothing cached — nothing to clean up */ });
  } else {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/service-worker.js').then((reg) => {
        reg.addEventListener('updatefound', () => {
          const newWorker = reg.installing;
          if (!newWorker) return;
          newWorker.addEventListener('statechange', () => {
            // New content installed and a controller exists → activate it.
            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
              newWorker.postMessage('SKIP_WAITING');
            }
          });
        });
      }).catch((err) => {
        // SW registration failure is non-fatal — app still works online.
        if (typeof console !== 'undefined') console.warn('[SW] registration failed:', err);
      });
    });

    // Reload when the new service worker takes over.
    let refreshing = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (refreshing) return;
      refreshing = true;
      window.location.reload();
    });
  }
}