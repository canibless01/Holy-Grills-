/** Match the backend's hg-event:<event UUID>:<door token> payload. */
export function eventQrPayload(raw: string, eventId: string): string | null {
  const value = raw.trim();
  if (value.startsWith('hg-event:')) {
    const parts = value.split(':');
    return parts.length === 3 && parts[1] === eventId && /^[a-f0-9-]{32,36}$/i.test(parts[2]) ? value : null;
  }
  const legacyPrefix = `HG-EVT-${eventId}-`;
  const token = value.startsWith(legacyPrefix) ? value.slice(legacyPrefix.length) : value;
  return /^[a-f0-9]{32}$/i.test(token) ? `hg-event:${eventId}:${token}` : null;
}
