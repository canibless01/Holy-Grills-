import APP_CONFIG from '@/config/app.config';
import { isNativeApp } from './platform';
import { isAllowedPaymentUrl } from '@/lib/safeNavigation';
import { nativeRoute, deliverNativeRoute } from './navigation';
import { flushNativeSession } from './secureSession';

const KEY = 'hg_native_payment_return_v1';
/** Preserve the existing verification route; never infer payment success locally. */
export async function launchPayment(url: string, returnPath: string) {
  if (!isAllowedPaymentUrl(url)) throw new Error('The payment link could not be verified.');
  if (!isNativeApp()) { window.location.assign(url); return; }
  const safe = nativeRoute(returnPath);
  if (!safe) throw new Error('The payment return could not be verified.');
  await flushNativeSession();
  localStorage.setItem(KEY, JSON.stringify({ path: safe, at: Date.now() }));
  const { Browser } = await import('@capacitor/browser');
  await Browser.open({ url, toolbarColor: '#FFF5F0' });
}
export function resumeNativePayment() {
  let pending;
  try { pending = JSON.parse(localStorage.getItem(KEY) || 'null'); } catch { /* ignore malformed local cache */ }
  localStorage.removeItem(KEY);
  if (!pending || Date.now() - pending.at > 24 * 3600 * 1000) return false;
  return deliverNativeRoute(pending.path, true);
}

export function paymentCallback(path: string) {
  return new URL(path, isNativeApp() ? APP_CONFIG.domain : window.location.origin).href;
}

export function clearNativePayment() { localStorage.removeItem(KEY); }
