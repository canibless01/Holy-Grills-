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
 *   1. Host level (the primary fix) — Vercel must serve the apex domain and
 *      redirect `www` to it:
 *        Project → Settings → Domains → `holygrills.online` = primary/connected
 *        `www.holygrills.online` → Redirect to `holygrills.online`
 *      Subscribers stay on the origin they already opted in on, so nobody has
 *      to resubscribe.
 *
 *   2. App level (this module, a SAFETY NET) — if a document is ever served
 *      from the www alias (dashboard redirect missing or mis-set, a stale
 *      cached document), `enforceCanonicalOrigin()` moves the browser to the
 *      apex origin before OneSignal is allowed to initialise. Path, query
 *      string and hash are preserved, so order/payment/referral links keep
 *      working.
 *
 * ── Why this module is BOUNCE-PROOF ─────────────────────────────────────────
 * A client-side origin redirect is dangerous by nature: if the host redirects
 * in the opposite direction, the two rules ping-pong and the visitor gets an
 * endless reload that never renders the page (exactly the 29 Oct symptom).
 * So a redirect here is **one attempt, never repeated**:
 *
 *   • the attempt is recorded on the alias origin (sessionStorage), and
 *   • a `hg_origin=bounced` marker travels with the redirect (host redirects
 *     preserve the query string).
 *
 * If we come back to the alias within BOUNCE_WINDOW_MS, we are being bounced:
 * the guard stands down, strips the marker and lets the app render. Push then
 * reports "open the canonical site" instead of pretending it can redirect —
 * the real fix at that point is the host setting, not a client loop.
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

/** Marker carried on the redirect target so a bounce back is provable. */
export const BOUNCE_PARAM = 'hg_origin';
export const BOUNCE_VALUE = 'bounced';

/** How long a recorded redirect attempt suppresses a second attempt. */
export const BOUNCE_WINDOW_MS = 60_000;

const ATTEMPT_STORAGE_KEY = 'hg_canonical_origin_attempt_at';

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

/** True when the URL carries the marker we add to our own redirect target. */
export const hasBounceMarker = (search: string | null | undefined): boolean => {
  try {
    return new URLSearchParams(search || '').get(BOUNCE_PARAM) === BOUNCE_VALUE;
  } catch {
    return false;
  }
};

const readAttemptAt = (): number => {
  try {
    return Number(globalThis.sessionStorage?.getItem(ATTEMPT_STORAGE_KEY)) || 0;
  } catch {
    return 0; // storage blocked (some private modes) — the URL marker still works
  }
};

/**
 * True when this document is being bounced: the URL says so, or we already
 * redirected from this alias origin a moment ago and are back.
 */
export const isOriginBounce = (
  location: LocationLike | null | undefined,
  now: number = Date.now(),
): boolean => {
  if (!location) return false;
  if (hasBounceMarker(location.search)) return true;
  const attemptedAt = readAttemptAt();
  return attemptedAt > 0 && now - attemptedAt < BOUNCE_WINDOW_MS;
};

/**
 * The absolute URL the browser should be sent to, or `null` when there is
 * nothing safe to do (already canonical, or being bounced).
 *
 * Pure function (no `window`/storage access) so it can be unit-tested without a
 * DOM: pass `bounced` in from `isOriginBounce()`.
 */
export const canonicalRedirectTarget = (
  location: LocationLike | null | undefined,
  options: { bounced?: boolean } = {},
): string | null => {
  if (!location || !isWwwAliasHost(location.hostname)) return null;
  // The host sent us back here after we redirected: do NOT redirect again.
  if (options.bounced || hasBounceMarker(location.search)) return null;
  const path = location.pathname && location.pathname.startsWith('/') ? location.pathname : '/';
  const params = new URLSearchParams(location.search || '');
  params.set(BOUNCE_PARAM, BOUNCE_VALUE);
  const search = `?${params.toString()}`;
  const hash = location.hash || '';
  return `${CANONICAL_ORIGIN}${path}${search}${hash}`;
};

let redirectStarted = false;

/**
 * Send the browser to the canonical origin when it is on the www alias.
 *
 * Returns `true` when a redirect was started — callers must not continue with
 * origin-bound work (OneSignal init, push subscribe) in that case.
 *
 * At most ONE redirect per document, and none at all while a bounce is in
 * progress, so this can never be the cause of an endless reload.
 */
export const enforceCanonicalOrigin = (): boolean => {
  if (redirectStarted) return true; // a navigation is already in flight
  if (typeof window === 'undefined' || !window.location) return false;
  const target = canonicalRedirectTarget(window.location, { bounced: isOriginBounce(window.location) });
  if (!target) return false;
  redirectStarted = true;
  try {
    globalThis.sessionStorage?.setItem(ATTEMPT_STORAGE_KEY, String(Date.now()));
  } catch { /* storage blocked — the URL marker still proves a bounce */ }
  try {
    // `replace` keeps the back button from bouncing between the two origins.
    window.location.replace(target);
  } catch {
    try { window.location.href = target; } catch { /* navigation unavailable */ }
  }
  return true;
};

/**
 * Remove our `hg_origin` marker from the address bar (no navigation).
 *
 * Called on every boot: on the canonical origin it keeps a shared/copied URL
 * clean, and on a bounce it removes the only trace of the guard.
 */
export const clearOriginMarker = (): void => {
  if (typeof window === 'undefined' || !window.location) return;
  const { search } = window.location;
  if (!hasBounceMarker(search)) return;
  try {
    const params = new URLSearchParams(search);
    params.delete(BOUNCE_PARAM);
    const query = params.toString();
    const clean = `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash || ''}`;
    window.history.replaceState(window.history.state, '', clean);
  } catch { /* history unavailable — a stray marker is harmless */ }
};

/** True while the page is served from an origin the push app is not set up for. */
export const isOnAliasedOrigin = (): boolean =>
  typeof window !== 'undefined' && Boolean(window.location) && isWwwAliasHost(window.location.hostname);

/** True when the host is bouncing us between the alias and the canonical host. */
export const isBeingOriginBounced = (): boolean =>
  typeof window !== 'undefined' && Boolean(window.location) && isOriginBounce(window.location);
