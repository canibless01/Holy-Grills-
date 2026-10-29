/**
 * Holy Grill — single served origin (web push origin alignment)
 * ============================================================================
 * The OneSignal web app is registered against ONE origin:
 *
 *     https://holygrills.online
 *
 * Browsers treat `https://www.holygrills.online` as a completely different
 * origin (same-origin policy), so the v16 page SDK refuses to initialise on the
 * www alias and logs an origin-mismatch error. Every subscriber that lands on
 * www therefore cannot enable push, and any player id created there would be
 * attributed to an origin the dashboard does not know about.
 *
 * Two things resolve that, and both point at the SAME origin:
 *
 *   1. Host level — Vercel redirects the `www` domain to the apex domain
 *      (Project → Settings → Domains → `www.holygrills.online` → Redirect to
 *      `holygrills.online`). This is the primary fix: subscribers stay on the
 *      origin they already opted in on, so nobody has to resubscribe.
 *
 *   2. App level (this module) — if a page is ever served from the www alias
 *      (dashboard redirect missing, a preview alias, a stale cached document),
 *      `enforceCanonicalOrigin()` moves the browser to the apex origin before
 *      OneSignal is allowed to initialise. Path, query string and hash are
 *      preserved, so order/payment/referral links keep working.
 *
 * Deliberately narrow: only the `www.holygrills.online` alias is normalised.
 * `localhost` (local push testing) and Vercel preview hosts are left alone so a
 * developer can still exercise the SDK.
 */

/** The ONE origin the OneSignal app is configured for. */
export const CANONICAL_HOST = 'holygrills.online';
export const CANONICAL_ORIGIN = `https://${CANONICAL_HOST}`;

/** The alias that must never serve the app. */
export const WWW_ALIAS_HOST = `www.${CANONICAL_HOST}`;

type LocationLike = {
  protocol?: string;
  hostname?: string;
  pathname?: string;
  search?: string;
  hash?: string;
};

/** True when `hostname` is the www alias of the canonical host. */
export const isWwwAliasHost = (hostname: string | null | undefined): boolean =>
  String(hostname || '').toLowerCase() === WWW_ALIAS_HOST;

/**
 * The absolute URL the browser should be sent to, or `null` when the current
 * location already is the canonical origin.
 *
 * Pure function (no `window` access) so it can be unit-tested without a DOM.
 */
export const canonicalRedirectTarget = (location: LocationLike | null | undefined): string | null => {
  if (!location || !isWwwAliasHost(location.hostname)) return null;
  const path = location.pathname && location.pathname.startsWith('/') ? location.pathname : '/';
  const search = location.search || '';
  const hash = location.hash || '';
  return `${CANONICAL_ORIGIN}${path}${search}${hash}`;
};

/**
 * Send the browser to the canonical origin when it is on the www alias.
 *
 * Returns `true` when a redirect was started — callers must not continue with
 * origin-bound work (OneSignal init, push subscribe) in that case.
 */
export const enforceCanonicalOrigin = (): boolean => {
  if (typeof window === 'undefined' || !window.location) return false;
  const target = canonicalRedirectTarget(window.location);
  if (!target) return false;
  try {
    // `replace` keeps the back button from bouncing between the two origins.
    window.location.replace(target);
  } catch {
    try { window.location.href = target; } catch { /* navigation unavailable */ }
  }
  return true;
};

/** True while the page is served from an origin the push app is not set up for. */
export const isOnAliasedOrigin = (): boolean =>
  typeof window !== 'undefined' && Boolean(window.location) && isWwwAliasHost(window.location.hostname);
