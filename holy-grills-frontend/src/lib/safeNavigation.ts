/**
 * Safe navigation (Phase 7 security review — findings S1, S7, S8)
 * ============================================================================
 * Three places in this app hand the browser a destination that came from
 * somewhere else, and `window.location`/`navigate` will happily act on whatever
 * they are given:
 *
 *   S1  payment redirects — `res.authorization_url` from the Flask backend
 *       (which gets it from Paystack). `window.location = 'javascript:…'` runs
 *       that code as part of this origin, so the value is checked to be https on
 *       a Paystack host before anything moves.
 *   S7  rider call links — `GET /orders/<id>/call-rider` returns the number to
 *       dial. Only `tel:` (and `https:` for click-to-chat links) is allowed, and
 *       the `tel:` payload is reduced to digits and a leading `+`.
 *   S8  CMS links — storefront sections carry `cta_url`/`destination`. External
 *       links open in a new tab with `noopener,noreferrer`; everything else is
 *       an in-app route. The promo popup had this rule; now all three consumers
 *       share it.
 *
 * Failing closed is deliberate: a value that does not match the policy is
 * refused (with a toast) rather than navigated to.
 */

/** Paystack's checkout host — the only place a card payment may redirect to. */
const PAYMENT_HOSTS = ['paystack.com'];

/** Parse a URL against the current origin; returns null for junk input. */
function parse(raw: unknown): URL | null {
  if (typeof raw !== 'string') return null;
  const trimmed = raw.trim();
  if (!trimmed) return null;
  try {
    return new URL(trimmed, window.location.origin);
  } catch {
    return null;
  }
}

/** True when a payment redirect is https and points at a Paystack host. */
export function isAllowedPaymentUrl(raw: unknown): boolean {
  const url = parse(raw);
  if (!url || url.protocol !== 'https:') return false;
  const host = url.hostname.toLowerCase();
  return PAYMENT_HOSTS.some((h) => host === h || host.endsWith(`.${h}`));
}

/**
 * A rider call link, normalised. `tel:` payloads are reduced to digits and a
 * leading `+`; `https://` links (click-to-chat) pass through unchanged. Anything
 * else returns null so the caller can show "no number available".
 *
 * The scheme test is done on the raw string on purpose: resolving first against
 * `window.location.origin` would turn junk like `"not a url"` into a perfectly
 * valid same-origin https URL, and the caller would navigate away instead of
 * reporting that there is no number.
 */
export function safeCallHref(raw: unknown): string | null {
  if (typeof raw !== 'string') return null;
  const trimmed = raw.trim();

  if (/^tel:/i.test(trimmed)) {
    const number = trimmed.slice(4).replace(/[^\d+]/g, '');
    return number.replace(/\D/g, '').length >= 6 ? `tel:${number}` : null;
  }

  if (/^https:\/\//i.test(trimmed)) {
    const url = parse(trimmed);
    return url ? url.href : null;
  }

  return null;
}

/**
 * Follow a CMS destination. Absolute http(s) links open in a new tab (with
 * `noopener,noreferrer` so the target cannot reach back through `window.opener`);
 * everything else is treated as an internal route.
 */
export function openCmsDestination(dest: unknown, navigate: (to: string) => void): void {
  if (typeof dest !== 'string') return;
  const trimmed = dest.trim();
  if (!trimmed) return;
  if (/^https?:\/\//i.test(trimmed)) {
    window.open(trimmed, '_blank', 'noopener,noreferrer');
    return;
  }
  navigate(trimmed);
}
