import { normalizeWhatsAppNumber } from './valueText';

/** Normal links preserve a user's tap and work without popup-script permission. */
export function buildWhatsAppShareUrl(caption: string, rawPhone?: unknown): string {
  const phone = normalizeWhatsAppNumber(rawPhone);
  const recipient = /^[1-9]\d{7,14}$/.test(phone) ? phone : '';
  return `https://wa.me/${recipient}?text=${encodeURIComponent(caption)}`;
}
