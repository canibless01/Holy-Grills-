// HolyGrill Live API Client — calls the real backend at holy-grills-backend.onrender.com
import { localStore, sessionStore } from '@/lib/storage';
import { queryClientInstance } from '@/lib/query-client';

// Configurable so a staging backend, a local Flask run or the dev proxy can be
// pointed at without a code change. The fallback is the production API.
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'https://holy-grills-backend.onrender.com/api';
const BASE_URL = API_BASE_URL;

const TOKEN_KEY = 'hg_access_token';
const REFRESH_KEY = 'hg_refresh_token';
let sessionVersion = 0;
// Share simultaneous JSON reads, never completed responses or mutations. Scope
// includes the actual token/campus/headers so accounts and campuses cannot join
// each other's in-flight private requests. Entries are removed on success/error.
const pendingReads = new Map<string, Promise<any>>();

// "Remember me" — when the user leaves the checkbox unchecked, tokens are
// stored in sessionStorage so they are cleared when the browser closes.
// When checked, tokens persist in localStorage across sessions.
const isRemember = () => localStore.getItem('hg_remember') !== '0';
const storage = () => isRemember() ? localStore : sessionStore;

export class ApiError extends Error {
  status: number;
  detail?: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

export function getToken() {
  return localStore.getItem(TOKEN_KEY) || sessionStore.getItem(TOKEN_KEY);
}

export function getRefreshToken() {
  return localStore.getItem(REFRESH_KEY) || sessionStore.getItem(REFRESH_KEY);
}

export function setTokens(access, refresh, rotating = false) {
  if (!rotating) sessionVersion += 1;
  // Clear both stores first so a stale token from the other storage can't
  // linger and cause isAuthenticated() to read a phantom session.
  localStore.removeItem(TOKEN_KEY);
  localStore.removeItem(REFRESH_KEY);
  sessionStore.removeItem(TOKEN_KEY);
  sessionStore.removeItem(REFRESH_KEY);
  const s = storage();
  if (access) s.setItem(TOKEN_KEY, access);
  if (refresh) s.setItem(REFRESH_KEY, refresh);
}

export function clearTokens() {
  sessionVersion += 1;
  localStore.removeItem(TOKEN_KEY);
  localStore.removeItem(REFRESH_KEY);
  sessionStore.removeItem(TOKEN_KEY);
  sessionStore.removeItem(REFRESH_KEY);
}

let refreshInFlight: Promise<string> | null = null;

async function performRefresh() {
  const refresh = getRefreshToken();
  if (!refresh) throw new ApiError(401, 'No refresh token');

  // Refresh with a timeout so a cold-starting backend can't hang the refresh
  // indefinitely. Transient failures (network error, timeout, 5xx) must NOT
  // clear the tokens — the access token may still be valid and the user
  // shouldn't be logged out just because the server was slow/unreachable.
  // Only a definitive 401/403 from /auth/refresh (refresh token invalid) clears.
  const doFetch = () => new Promise((resolve, reject) => {
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), 12000);
    fetch(`${BASE_URL}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
      signal: controller.signal,
    }).then((res) => { clearTimeout(t); resolve(res); })
      .catch((e) => { clearTimeout(t); reject(e); });
  });

  let res;
  try { res = await doFetch(); }
  catch (e) {
    throw new ApiError(0, e.name === 'AbortError' ? 'Refresh timed out — the server may be starting up.' : (e.message || 'Network error during refresh'));
  }

  if (res.status === 401 || res.status === 403) {
    // The backend reserves these statuses for an actual rejected refresh;
    // provider outages use 429/5xx. Stop retrying invalid/revoked credentials.
    const detail = await res.json().catch(() => null);
    if (getRefreshToken() === refresh) clearTokens();
    throw new ApiError(res.status, detail?.error || 'Session refresh failed — please retry, or re-login if the issue persists.', detail);
  }
  if (!res.ok) {
    // 5xx or other — keep tokens; this is likely a transient backend issue.
    throw new ApiError(res.status, `Refresh failed (${res.status}) — retry shortly`);
  }

  const data = await res.json().catch(() => null);
  if (typeof data?.access_token !== 'string' || !data.access_token.trim() || (data.refresh_token != null && (typeof data.refresh_token !== 'string' || !data.refresh_token.trim()))) {
    throw new ApiError(0, 'Session refresh unavailable — please retry.');
  }
  // A logout or another sign-in while the request was pending must win.
  if (getRefreshToken() !== refresh) throw new ApiError(0, 'Session changed — please retry.');
  setTokens(data.access_token, data.refresh_token || refresh, true);
  return data.access_token;
}

// One rotation for a burst of expired requests. Late 401 responses reuse the
// token already refreshed by an earlier request rather than rotating again.
async function refreshToken(rejectedToken: string) {
  if (getToken() && getToken() !== rejectedToken) return getToken();
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => { refreshInFlight = null; });
  }
  return refreshInFlight;
}

/** fetch options plus the internal single-retry flag. */
type RequestOptions = RequestInit & { _retried?: boolean; timeoutMs?: number };

const PUBLIC_STOREFRONT_READS = new Set([
  '/storefront/sections', '/storefront/banners', '/storefront/early-supporters',
  '/storefront/config/public', '/storefront/feature-flags',
]);

/**
 * Campus scope headers derived from the same localStorage state the admin
 * campus switcher writes (hg_admin_campus_id / hg_admin_scope_all).
 *
 *  - A selected campus is sent as X-Campus-ID on EVERY request (reads + writes).
 *  - "All Campuses" has no campus id to send, and an absent X-Campus-ID is
 *    ambiguous server-side (old client vs. an explicit global choice). On
 *    writes we therefore add X-Campus-Scope: global, so the backend stores
 *    campus_id NULL instead of falling back to the super admin's profile
 *    campus. Super admins never send their profile campus as a scope.
 *  - Campus admins keep sending their own profile campus; guests send the
 *    campus-gate selection.
 */
function campusScopeHeaders(
  storedToken: string | null,
  method?: string,
  opts: { publicRead?: boolean } = {},
): Record<string, string> {
  const role = storedToken ? localStore.getItem('hg_user_role') : null;
  const isSuperAdmin = role === 'super_admin';
  const adminAll = !!storedToken && localStore.getItem('hg_admin_scope_all') === '1';
  const adminCampusId = storedToken && !adminAll ? localStore.getItem('hg_admin_campus_id') : null;
  const userCampusId = storedToken && !isSuperAdmin ? localStore.getItem('hg_user_campus_id') : null;
  const guestCampusId = !storedToken ? localStore.getItem('hg_campus_id') : null;
  // Public reads strip the auth token, so the backend treats a logged-in
  // super_admin as a guest. Without a campus header the response would only
  // contain global rows; fall back to the gate/profile selection for reads.
  const publicReadCampus = opts.publicRead && isSuperAdmin && !adminCampusId
    ? (localStore.getItem('hg_campus_id') || localStore.getItem('hg_user_campus_id'))
    : null;
  const campusHeader = adminCampusId || userCampusId || guestCampusId || publicReadCampus;
  const headers: Record<string, string> = {};
  if (campusHeader) headers['X-Campus-ID'] = campusHeader;
  const verb = (method || 'GET').toUpperCase();
  const isWrite = verb !== 'GET' && verb !== 'HEAD';
  if (storedToken && isSuperAdmin && adminAll && isWrite) {
    headers['X-Campus-Scope'] = 'global';
  }
  return headers;
}

export function getPublicCampusScope() {
  return campusScopeHeaders(getToken(), 'GET', { publicRead: true })['X-Campus-ID'] || null;
}

async function request(path: string, options: RequestOptions = {}) {
  const { timeoutMs = 12000, ...fetchOptions } = options;
  const storedToken = getToken();
  const parsedPath = new URL(path, 'https://app.invalid');
  const publicRead = (!options.method || options.method === 'GET') && PUBLIC_STOREFRONT_READS.has(parsedPath.pathname)
    && !['1', 'true', 'yes'].includes((parsedPath.searchParams.get('include_inactive') || '').toLowerCase());
  // Published content has the same public access regardless of saved session.
  // Do not make every banner wait for Auth verification/token recovery. The
  // stored campus remains a presentation hint; management reads still verify.
  const token = publicRead ? null : storedToken;
  const version = sessionVersion;
  // NOTE: a 401 on a data fetch must NOT log the user out. The refresh attempt
  // below recovers a valid session whose access token expired; if refresh also
  // fails we surface a retryable error instead of clearing tokens, so a cold
  // or slow backend never bounces the user to /login mid-session.
  // Domain 0 — campus scope. Guests send X-Campus-ID from the campus gate
  // (hg_campus_id). Authenticated super-admins send X-Campus-ID from the
  // admin campus selector (hg_admin_campus_id) so they can view/manage a
  // campus other than their own, and X-Campus-Scope: global on writes when
  // "All Campuses" is selected. Regular authenticated users get
  // X-Campus-ID from their persisted profile campus (hg_user_campus_id,
  // saved by HolyGrillContext) — the storefront/kitchen-status endpoints
  // need campus context even for signed-in users, not just guests.
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...campusScopeHeaders(storedToken, options.method, { publicRead }),
    ...options.headers,
  };

  // Bounded deadline. Public storefront reads can allow a slower cold start;
  // authenticated and financial requests keep the existing 12-second default.
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  const abortFromCaller = () => controller.abort();
  options.signal?.addEventListener('abort', abortFromCaller, { once: true });
  if (options.signal?.aborted) controller.abort();

  let res;
  try {
    res = await fetch(`${BASE_URL}${path}`, { ...fetchOptions, headers, signal: controller.signal });
  } catch (e) {
    clearTimeout(timeoutId);
    options.signal?.removeEventListener('abort', abortFromCaller);
    if (e.name === 'AbortError') throw new ApiError(0, 'Request timed out — the server may be starting up. Try again in a moment.');
    throw new ApiError(0, e.message || 'Network error');
  }
  clearTimeout(timeoutId);
  options.signal?.removeEventListener('abort', abortFromCaller);

  // Auto-refresh on 401 (once). On a transient refresh failure (network/5xx)
  // keep the tokens so the user isn't logged out by a slow backend — surface
  // a retryable error instead. Only clear on a definitive auth rejection.
  if (res.status === 401 && token && !options._retried) {
    if (version !== sessionVersion) throw new ApiError(0, 'Session changed — please retry.');
    try {
      await refreshToken(token);
      if (version !== sessionVersion) throw new ApiError(0, 'Session changed — please retry.');
      return request(path, { ...options, _retried: true });
    } catch (refreshErr) {
      if (refreshErr.status === 401 || refreshErr.status === 403) {
        throw refreshErr;
      }
      throw new ApiError(refreshErr.status || 0, refreshErr.message || 'Session refresh unavailable — please retry.');
    }
  }

  const data = await res.json().catch(() => null);

  if (!res.ok) {
    throw new ApiError(res.status, data?.error || data?.message || `Request failed (${res.status})`, data);
  }

  // Admin publication must appear immediately even when Home has a fresh
  // cached snapshot. Private/financial requests never invalidate this cache.
  const publishedResource = parsedPath.pathname.match(/^\/storefront\/(sections|banners|early-supporters)(?:\/|$)/)?.[1];
  if (publishedResource && options.method && !['GET', 'HEAD'].includes(options.method)) {
    void queryClientInstance.invalidateQueries({
      queryKey: ['published-storefront'],
      predicate: query => query.queryKey[2] === publishedResource,
    });
  }
  return data;
}

// Raw-text request — for endpoints that return CSV/plain-text instead of JSON
// (e.g. GET /analytics/export). Uses the same auth + campus headers + timeout
// as request(), but returns the response body as a string instead of parsing
// it as JSON.
async function requestRaw(path: string, options: RequestOptions = {}) {
  const token = getToken();
  const version = sessionVersion;
  // Same campus contract as request(): selected campus -> X-Campus-ID on
  // every call; super-admin "All Campuses" -> X-Campus-Scope: global on
  // writes so CSV-triggered exports/mutations carry the explicit scope.
  const headers = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...campusScopeHeaders(token, options.method),
    ...options.headers,
  };

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 12000);

  let res;
  try {
    res = await fetch(`${BASE_URL}${path}`, { ...options, headers, signal: controller.signal });
  } catch (e) {
    clearTimeout(timeoutId);
    if (e.name === 'AbortError') throw new ApiError(0, 'Request timed out — the server may be starting up. Try again in a moment.');
    throw new ApiError(0, e.message || 'Network error');
  }
  clearTimeout(timeoutId);

  if (res.status === 401 && token && !options._retried) {
    if (version !== sessionVersion) throw new ApiError(0, 'Session changed — please retry.');
    try {
      await refreshToken(token);
      if (version !== sessionVersion) throw new ApiError(0, 'Session changed — please retry.');
      return requestRaw(path, { ...options, _retried: true });
    } catch (refreshErr) {
      if (refreshErr.status === 401 || refreshErr.status === 403) {
        throw refreshErr;
      }
      throw new ApiError(refreshErr.status || 0, refreshErr.message || 'Session refresh unavailable — please retry.');
    }
  }

  const text = await res.text();

  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try { const data = JSON.parse(text); msg = data?.error || data?.message || msg; } catch { /* not JSON — keep generic */ }
    throw new ApiError(res.status, msg, text);
  }

  return text;
}

export const apiClient = {
  /**
   * `headers` is merged LAST, so a caller can state a campus explicitly and
   * override the one apiClient derived from storage. Used by the checkout
   * kitchen-status read, which must be scoped to the campus the guest is
   * actually ordering from even if the persisted header has not landed yet.
   */
  get(path: string, params?: Record<string, unknown>, headers?: Record<string, string>, options?: { timeoutMs?: number }) {
    const qs = params ? '?' + new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '') as [string, string][]
    ).toString() : '';
    const scope = campusScopeHeaders(getToken(), 'GET');
    const key = JSON.stringify([path + qs, sessionVersion, getToken(), scope, headers || {}, options?.timeoutMs || 12000]);
    const existing = pendingReads.get(key);
    if (existing) return existing;
    const pending = request(path + qs, { ...options, ...(headers ? { headers } : {}) }).finally(() => {
      if (pendingReads.get(key) === pending) pendingReads.delete(key);
    });
    pendingReads.set(key, pending);
    return pending;
  },
  post(path: string, body?: unknown, options?: { timeoutMs?: number; signal?: AbortSignal }) {
    return request(path, { ...options, method: 'POST', body: body ? JSON.stringify(body) : undefined });
  },
  patch(path: string, body?: unknown) {
    return request(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined });
  },
  getRaw(path: string, params?: Record<string, unknown>) {
    const qs = params ? '?' + new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '') as [string, string][]
    ).toString() : '';
    return requestRaw(path + qs);
  },
  delete(path: string, body?: unknown) {
    return request(path, { method: 'DELETE', body: body ? JSON.stringify(body) : undefined });
  },
  setTokens,
  clearTokens,
  getToken,
};

// Auth helper — login and store tokens
export async function login(email: string, password: string) {
  const res = await fetch(`${BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, data?.error || 'Login failed', data);
  if (data.access_token) setTokens(data.access_token, data.refresh_token);
  return data;
}

// Check if we have a token
export function isAuthenticated() {
  return !!getToken();
}
