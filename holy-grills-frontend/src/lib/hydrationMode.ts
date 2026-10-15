/**
 * Hydration mode (Track B)
 * ============================================================================
 * A page load is "hydrating a pre-render" when the HTML arriving from the host
 * was rendered at build time for the URL the browser asked for. The pre-render
 * runs with empty storage (src/lib/storage.ts), so its markup always shows the
 * signed-out, no-campus state.
 *
 * Anything that reads storage during the FIRST render must therefore return the
 * empty-storage answer while that markup is being hydrated, otherwise React
 * compares two different trees and reports a hydration mismatch. Effects then
 * adopt the real values immediately after mount, which is where the app already
 * syncs the session (see HolyGrillContext's init effect).
 *
 * `scripts/prerender.mjs` writes the stamp; src/main.tsx uses the same helper to
 * decide between hydrateRoot and createRoot.
 */

/** Attribute the pre-render writes on #root, e.g. data-prerendered-route="/faq". */
export const PRERENDER_STAMP_ATTR = 'data-prerendered-route';

/** The path being rendered, normalised the way the stamp is written. */
export function currentPath(): string {
  if (typeof window === 'undefined') return '/';
  return window.location.pathname.replace(/\/+$/, '') || '/';
}

/** True when the served HTML belongs to the current URL. */
export function isHydratingPrerender(): boolean {
  if (typeof document === 'undefined') return false;
  const stamp = document.getElementById('root')?.getAttribute(PRERENDER_STAMP_ATTR);
  return !!stamp && stamp === currentPath();
}
