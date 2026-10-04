// Analytics gate — wraps the platform event tracker so events only fire when
// the user accepted analytics cookies. Decline (essential-only) makes track()
// a no-op. No third-party analytics SDK is installed today; when you add GA,
// Meta Pixel or PostHog, route their calls through here so consent gates them.
import { base44 } from '@/api/base44Client';
import { hasAnalyticsConsent } from './cookieConsent';

export function track(eventName, properties) {
  if (!hasAnalyticsConsent()) return null;
  try {
    return base44.analytics.track({ eventName, properties: properties || {} });
  } catch {
    return null;
  }
}