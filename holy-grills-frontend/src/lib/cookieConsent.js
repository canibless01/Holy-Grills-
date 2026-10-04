// Cookie consent — a dated, per-category record in localStorage.
// Accepting or declining persists { essential, analytics, date } and the
// banner never reappears afterwards. Other modules read hasAnalyticsConsent()
// to gate non-essential tracking. Essential (auth, cart, order updates) is
// always on and never depended on this consent.

const KEY = 'hg_cookie_consent';

export function getConsent() {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

// Analytics covers event tracking / page-view measurement only. There is no
// third-party analytics SDK (GA, Meta Pixel, PostHog…) installed today, so
// this gates the platform's built-in event tracker and is ready to gate any
// future SDK. It does NOT gate order-update push notifications (essential).
export function hasAnalyticsConsent() {
  const c = getConsent();
  return !!c && c.analytics === true;
}

export function setConsent({ analytics }) {
  const record = { essential: true, analytics: !!analytics, date: new Date().toISOString() };
  try { localStorage.setItem(KEY, JSON.stringify(record)); } catch { /* ignore */ }
  notify(record);
  return record;
}

const listeners = new Set();
export function onConsentChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
function notify(r) {
  listeners.forEach((fn) => { try { fn(r); } catch { /* ignore */ } });
}