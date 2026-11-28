import APP_CONFIG from '@/config/app.config';

/** Untrusted URLs from Android intents/provider notifications may only open app routes. */
export function nativeRoute(raw: unknown): string | null {
  if (typeof raw !== 'string' || /[\u0000-\u001f\\]/.test(raw) || raw.startsWith('//')) return null;
  let url: URL;
  try { url = new URL(raw, 'https://holygrills.online'); } catch { return null; }
  if (url.username || url.password) return null;
  const hosts = new Set(['holygrills.online', 'www.holygrills.online', 'localhost']);
  try { if (APP_CONFIG.domain) hosts.add(new URL(APP_CONFIG.domain).hostname); } catch { /* invalid config is not trusted */ }
  if (!(url.protocol === 'https:' && hosts.has(url.hostname)) && !(url.protocol === 'holygrills:' && url.hostname === 'app')) return null;
  if (!/^\/(?:$|(?:team|admin|community-manager|event-manager|kitchen|rider|r|signup|newsletter|android|cart|checkout|order-confirmation|addresses|notifications|notification-preferences|order-locks|hp-education|hall-of-fame|catering|faq|contact|terms|our-story|menu)(?:\/|$)|dashboard(?:\/|$)|orders(?:\/|$)|track-orders(?:\/|$)|wallet(?:\/|$)|rewards(?:\/|$)|profile(?:\/|$)|events(?:\/|$)|marketplace(?:\/|$)|register(?:\/|$)|login(?:\/|$)|reset-password(?:\/|$)|referrals(?:\/|$)|leaderboard(?:\/|$)|squads(?:\/|$)|streak(?:\/|$))/.test(url.pathname)) return null;
  return url.pathname + url.search + url.hash;
}
let pendingRoute: { path: string; paymentReturn: boolean } | null = null;
let handler: ((path: string, paymentReturn: boolean) => void) | null = null;
export function deliverNativeRoute(raw: unknown, paymentReturn = false) {
  const route = nativeRoute(raw);
  if (!route) return false;
  const params = new URL(route, 'https://holygrills.online').searchParams;
  const verificationReturn = paymentReturn || ['reference', 'trxref', 'payment_return', 'auto_funding', 'delivery_pass'].some(key => params.has(key));
  if (handler) handler(route, verificationReturn); else pendingRoute = { path: route, paymentReturn: verificationReturn };
  return true;
}
export function listenNativeRoutes(callback: (path: string, paymentReturn: boolean) => void) {
  handler = callback;
  if (pendingRoute) { const route = pendingRoute; pendingRoute = null; callback(route.path, route.paymentReturn); }
  return () => { if (handler === callback) handler = null; };
}
