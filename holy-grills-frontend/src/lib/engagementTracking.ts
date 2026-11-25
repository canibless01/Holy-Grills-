import { API_BASE_URL, getToken } from './apiClient';
import { localStore } from './storage';
import { hasAnalyticsConsent } from './cookieConsent';
const VISITOR_KEY = 'hg_analytics_visitor_v1';
const EXACT = new Set(['/', '/menu','/checkout','/register','/login','/dashboard','/rewards','/wallet','/profile','/orders','/events','/marketplace','/referrals','/streak','/squads','/our-story','/faq','/contact']);
export function engagementPath(pathname: string): string | null {
  if (EXACT.has(pathname)) return pathname;
  for (const [prefix,bucket] of [['/menu/','/menu/:item'],['/orders/','/orders/:order'],['/events/','/events/:event'],['/marketplace/','/marketplace/:item']]) {
    if (pathname.startsWith(prefix) && !pathname.slice(prefix.length).includes('/')) return bucket;
  }
  return null;
}
export function clearEngagementVisitor() { localStore.removeItem(VISITOR_KEY); }
export async function recordEngagementPage(id: string, path: string, campus: string, authenticated: boolean) {
  if (!hasAnalyticsConsent()) return;
  let visitor = localStore.getItem(VISITOR_KEY);
  if (!visitor) { visitor = crypto.randomUUID(); localStore.setItem(VISITOR_KEY, visitor); }
  const token = authenticated ? getToken() : null;
  const result = await fetch(`${API_BASE_URL}/engagement/page-view`, {
    method: 'POST', credentials: 'omit', keepalive: true,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify({ id, visitor_id: visitor, path, campus_id: campus }),
  });
  if (result.status >= 500) throw new Error('Engagement service unavailable');
}
