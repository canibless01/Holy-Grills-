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

/** Organizer admission accepts an emailed ticket payload or a pasted ticket ID. */
export function ticketQrPayload(raw: string, eventId: string): string | null {
  const value = raw.trim();
  const parts = value.startsWith('hg-event:') ? value.split(':') : null;
  const ticketId = parts ? parts[2] : value;
  if (parts && (parts.length !== 3 || parts[1] !== eventId)) return null;
  return /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(ticketId || '')
    ? `hg-event:${eventId}:${ticketId}` : null;
}
