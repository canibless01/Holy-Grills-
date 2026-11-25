/** Device consent may carry into an account created after the opt-in.
 * An older account's saved opt-out must never be silently re-enabled.
 */
export function canAdoptGuestPushConsent(createdAt: unknown, consentAt: number, now = Date.now()): boolean {
  if (typeof createdAt !== 'string' || !Number.isFinite(consentAt) || consentAt <= 0 || consentAt > now) return false;
  const created = Date.parse(createdAt);
  return Number.isFinite(created) && created >= consentAt && created <= now + 60000;
}
