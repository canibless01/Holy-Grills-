import { useEffect, type DependencyList } from 'react';

// Refetch reads after a real browser return/reconnection. Never reload the
// document or remount forms. One shared listener coalesces browser events.
const listeners = new Set<() => void>();
let hiddenAt: number | null = null;
let lastRefresh = 0;
const refresh = () => {
  if (document.visibilityState === 'hidden' || Date.now() - lastRefresh < 15000) return;
  lastRefresh = Date.now();
  for (const listener of listeners) listener();
};
const visibility = () => {
  if (document.visibilityState === 'hidden') hiddenAt = Date.now();
  else if (hiddenAt !== null && Date.now() - hiddenAt >= 5000) { hiddenAt = null; refresh(); }
};
const pageShow = (event: PageTransitionEvent) => { if (event.persisted) refresh(); };
const subscribe = (listener: () => void) => {
  if (!listeners.size) {
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('pageshow', pageShow);
    window.addEventListener('online', refresh);
  }
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
    if (!listeners.size) {
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('pageshow', pageShow);
      window.removeEventListener('online', refresh);
      hiddenAt = null;
    }
  };
};

export function useResumeEffect(load: (background: boolean) => void | (() => void), dependencies: DependencyList) {
  useEffect(() => {
    let cleanup = load(false);
    const unsubscribe = subscribe(() => { if (typeof cleanup === 'function') cleanup(); cleanup = load(true); });
    return () => { unsubscribe(); if (typeof cleanup === 'function') cleanup(); };
    // The caller supplies every request dependency, as with useEffect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, dependencies);
}
