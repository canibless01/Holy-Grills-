// HolyGrill Live API Client — calls the real backend at holy-grills-backend.onrender.com
import { localStore, sessionStore } from '@/lib/storage';

export const API_BASE_URL = 'https://holy-grills-backend.onrender.com/api';
const BASE_URL = API_BASE_URL;

const TOKEN_KEY = 'hg_access_token';
const REFRESH_KEY = 'hg_refresh_token';

// "Remember me" — when the user leaves the checkbox unchecked, tokens are
// stored in sessionStorage so they are cleared when the browser closes.
// When checked, tokens persist in localStorage across sessions.
const isRemember = () => localStore.getItem('hg_remember') === '1';
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

export function setTokens(access, refresh) {
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
  localStore.removeItem(TOKEN_KEY);
  localStore.removeItem(REFRESH_KEY);
  sessionStore.removeItem(TOKEN_KEY);
  sessionStore.removeItem(REFRESH_KEY);
}

async function refreshToken() {
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
    // Don't clear tokens — a cold/slow backend can return 401 transiently even
    // for a valid session. Surface a retryable error so the page can retry
    // without losing the session. The user can still manually re-login.
    throw new ApiError(401, 'Session refresh failed — please retry, or re-login if the issue persists.');
  }
  if (!res.ok) {
    // 5xx or other — keep tokens; this is likely a transient backend issue.
    throw new ApiError(res.status, `Refresh failed (${res.status}) — retry shortly`);
  }

  const data = await res.json().catch(() => null);
  if (data?.access_token) setTokens(data.access_token, data.refresh_token || refresh);
  return data?.access_token;
}

/** fetch options plus the internal single-retry flag. */
type RequestOptions = RequestInit & { _retried?: boolean };

async function request(path: string, options: RequestOptions = {}) {
  const token = getToken();
  // NOTE: a 401 on a data fetch must NOT log the user out. The refresh attempt
  // below recovers a valid session whose access token expired; if refresh also
  // fails we surface a retryable error instead of clearing tokens, so a cold
  // or slow backend never bounces the user to /login mid-session.
  // Domain 0 — campus scope. Guests send X-Campus-ID from the campus gate
  // (hg_campus_id). Authenticated super-admins send X-Campus-ID from the
  // admin campus selector (hg_admin_campus_id) so they can view/manage a
  // campus other than their own. Regular authenticated users get
  // X-Campus-ID from their persisted profile campus (hg_user_campus_id,
  // saved by HolyGrillContext) — the storefront/kitchen-status endpoints
  // need campus context even for signed-in users, not just guests.
  const adminCampusId = token && localStore.getItem('hg_admin_campus_id');
  const userCampusId = token && localStore.getItem('hg_user_campus_id');
  const guestCampusId = !token && localStore.getItem('hg_campus_id');
  const campusHeader = adminCampusId || userCampusId || guestCampusId;
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(campusHeader ? { 'X-Campus-ID': campusHeader } : {}),
    ...options.headers,
  };

  // 12s timeout — fails fast on a cold-starting backend instead of hanging
  // indefinitely and freezing the UI behind a loading state.
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

  // Auto-refresh on 401 (once). On a transient refresh failure (network/5xx)
  // keep the tokens so the user isn't logged out by a slow backend — surface
  // a retryable error instead. Only clear on a definitive auth rejection.
  if (res.status === 401 && token && !options._retried) {
    try {
      await refreshToken();
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

  return data;
}

// Raw-text request — for endpoints that return CSV/plain-text instead of JSON
// (e.g. GET /analytics/export). Uses the same auth + campus headers + timeout
// as request(), but returns the response body as a string instead of parsing
// it as JSON.
async function requestRaw(path: string, options: RequestOptions = {}) {
  const token = getToken();
  const adminCampusId = token && localStore.getItem('hg_admin_campus_id');
  const userCampusId = token && localStore.getItem('hg_user_campus_id');
  const guestCampusId = !token && localStore.getItem('hg_campus_id');
  const campusHeader = adminCampusId || userCampusId || guestCampusId;
  const headers = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(campusHeader ? { 'X-Campus-ID': campusHeader } : {}),
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
    try {
      await refreshToken();
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
  get(path: string, params?: Record<string, unknown>) {
    const qs = params ? '?' + new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '') as [string, string][]
    ).toString() : '';
    return request(path + qs);
  },
  post(path: string, body?: unknown) {
    return request(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined });
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