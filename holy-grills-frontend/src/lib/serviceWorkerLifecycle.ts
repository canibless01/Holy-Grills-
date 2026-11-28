const WORKER_PATH = '/service-worker.js';

function sameScript(left: string, right: string) {
  try {
    const a = new URL(left, window.location.origin);
    const b = new URL(right, window.location.origin);
    return a.origin === b.origin && a.pathname === b.pathname;
  } catch { return false; }
}

// OneSignal adds appId/sdkVersion to the shared worker URL. Re-register that
// active URL on later visits instead of replacing it with the plain PWA URL.
export async function registerAppServiceWorker(workers = navigator.serviceWorker) {
  const registration = await workers.getRegistration('/');
  const active = registration?.active?.scriptURL;
  return workers.register(active && sameScript(active, WORKER_PATH) ? active : WORKER_PATH);
}

export function watchServiceWorkerController(
  workers = navigator.serviceWorker,
  reload = () => window.location.reload(),
) {
  let previous = workers.controller?.scriptURL || null;
  let refreshing = false;
  const changed = () => {
    const current = workers.controller?.scriptURL || null;
    const before = previous;
    previous = current;
    // First claim and OneSignal's query-only registration changes do not
    // change the application bundle. Reloading here loses forms and caches
    // and makes the app and SDK repeatedly replace each other's worker.
    if (!before || !current) return;
    if (before !== current && sameScript(before, current)) return;
    if (refreshing) return;
    refreshing = true;
    reload();
  };
  workers.addEventListener('controllerchange', changed);
  return () => workers.removeEventListener('controllerchange', changed);
}
