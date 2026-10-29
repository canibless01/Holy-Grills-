import ReactDOM from 'react-dom/client'
import App from '@/App'
import { isHydratingPrerender } from '@/lib/hydrationMode'
import { loadMessages } from '@/lib/messages'
import { clearOriginMarker, enforceCanonicalOrigin, isBeingOriginBounced } from '@/lib/canonicalOrigin'
import '@fontsource-variable/nunito'
import '@/index.css'

/**
 * Single-origin guard — runs before anything renders or registers a worker.
 *
 * The OneSignal web app is configured for exactly one origin
 * (https://holygrills.online). A document served from the www alias cannot
 * initialize the push SDK there (the browser treats the two hosts as different
 * origins), so move the visitor to the configured origin before the app — or
 * the SDK — starts. Path, query string and hash are preserved, so order,
 * payment-return and referral links keep working.
 *
 * See src/lib/canonicalOrigin.ts and docs/WEB_PUSH_ORIGIN_ALIGNMENT_2026_10_29.md.
 * When a redirect starts, the rest of boot is skipped: nothing mounts and no
 * service worker is registered on an origin push cannot use.
 */
function boot() {
  // Copy catalog (GET /api/messages, see src/lib/messages.ts). Fire-and-forget:
  // every t() renders its bundled fallback until this lands, so nothing waits on it.
  void loadMessages()

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

      // First installation should claim the open page without interrupting its
      // forms/guest lookup. Reload only when an already controlled page updates.
      let refreshing = false;
      let wasControlled = Boolean(navigator.serviceWorker.controller);
      navigator.serviceWorker.addEventListener('controllerchange', () => {
        if (!wasControlled) { wasControlled = true; return; }
        if (refreshing) return;
        refreshing = true;
        window.location.reload();
      });
    }
  }
}

if (!enforceCanonicalOrigin()) {
  // A redirect would have returned true. Reaching here means either the page is
  // already on the canonical origin, or we have just been bounced back by the
  // host — in which case the guard stands down permanently instead of
  // reloading forever, and the app must render (push reports the real reason).
  clearOriginMarker();
  if (isBeingOriginBounced()) {
    console.warn(
      '[origin] The site is being served from www.holygrills.online and the redirect '
      + 'back to https://holygrills.online is looping, so the app was rendered here '
      + 'instead of reloading. Fix the host: make holygrills.online primary and point '
      + 'www.holygrills.online at it (one direction only). Push stays unavailable on '
      + 'this origin until then.',
    );
  }
  boot();
}
