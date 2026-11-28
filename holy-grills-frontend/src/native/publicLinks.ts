import APP_CONFIG from '@/config/app.config';
import { isNativeApp } from './platform';

/** Links shared outside Android must point to the public site, never WebView localhost. */
export function publicSiteUrl(path = '/') {
  const origin = isNativeApp() || typeof window === 'undefined' ? APP_CONFIG.domain : window.location.origin;
  return new URL(path, origin || 'https://holygrills.online').href;
}
export function publicShareUrl(raw: string) {
  if (!isNativeApp()) return raw;
  try {
    const url = new URL(raw);
    if (url.hostname === 'localhost' && ['http:', 'https:'].includes(url.protocol)) return publicSiteUrl(url.pathname + url.search + url.hash);
  } catch { /* Normal fallback remains the public home page. */ }
  return raw;
}
