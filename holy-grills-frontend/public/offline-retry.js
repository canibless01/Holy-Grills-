/* Kept external so the production CSP can run offline recovery. */
(function () {
  const btn = document.getElementById('retry-btn');
  const status = document.getElementById('status');
  let checking = false;
  async function retry() {
    if (checking) return;
    checking = true; btn.disabled = true; btn.classList.add('loading');
    status.textContent = 'Checking connection…';
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch('/manifest.json?reconnect=' + Date.now(), {cache:'no-store', signal:controller.signal});
      if (!response.ok) throw new Error('offline');
      await response.json();
      status.textContent = 'Back online. Reloading…';
      const target = location.pathname === '/offline.html' ? '/' : location.pathname + location.search + location.hash;
      location.replace(target);
    } catch (_) {
      status.textContent = 'Still offline — please check your connection and try again.';
    } finally {
      clearTimeout(timeout); checking = false; btn.disabled = false; btn.classList.remove('loading');
    }
  }
  btn.addEventListener('click', retry);
  window.addEventListener('online', retry);
}());
