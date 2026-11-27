/** Native-only gesture adapter. Never intercept scrolling, maps, forms or pinch gestures. */
export function installPullRefresh(onProgress: (distance: number) => void, onRefresh: () => Promise<void>) {
  let start: { x: number; y: number } | null = null;
  let distance = 0, busy = false;
  const reset = () => { start = null; distance = 0; onProgress(0); };
  const begin = (event: TouchEvent) => {
    if (busy || event.touches.length !== 1 || window.scrollY > 0) return;
    const target = event.target instanceof Element ? event.target : null;
    if (document.querySelector('[aria-modal="true"]') || target?.closest('input,textarea,select,button,a,[role="listbox"],[data-native-no-refresh],.gm-style,[aria-label="Choose your delivery pin on Google Maps"]')) return;
    for (let node = target; node; node = node.parentElement) if (node.scrollTop > 0) return;
    start = { x: event.touches[0].clientX, y: event.touches[0].clientY };
  };
  const move = (event: TouchEvent) => {
    if (!start) return;
    if (event.touches.length !== 1 || window.scrollY > 0) { reset(); return; }
    const dx = Math.abs(event.touches[0].clientX - start.x), dy = event.touches[0].clientY - start.y;
    if (dx > 30 || dy < 0) { reset(); return; }
    distance = Math.min(dy, 120);
    if (distance > 20) { event.preventDefault(); onProgress(distance); }
  };
  const end = () => {
    const shouldRefresh = !!start && distance >= 80 && !busy;
    reset();
    if (shouldRefresh) {
      busy = true;
      void onRefresh().finally(() => { busy = false; });
    }
  };
  window.addEventListener('touchstart', begin, { passive: true });
  window.addEventListener('touchmove', move, { passive: false });
  window.addEventListener('touchend', end);
  window.addEventListener('touchcancel', reset);
  return () => {
    window.removeEventListener('touchstart', begin); window.removeEventListener('touchmove', move);
    window.removeEventListener('touchend', end); window.removeEventListener('touchcancel', reset);
  };
}
