/** A new flyer revision is visible immediately; the same revision repeats daily. */
export const POPUP_INTERVAL_MS = 24 * 60 * 60 * 1000;
export function popupRevision(section: any): string {
  return JSON.stringify([section.updated_at || '', section.title || '', section.content || {}, section.image_url || '']);
}
export function popupReceiptKey(campus: string, placement: string, id: string): string {
  return `hg_popup_seen_v2_${campus}_${placement}_${id}`;
}
export function popupDue(receipt: unknown, revision: string, now = Date.now()): boolean {
  if (!receipt || typeof receipt !== 'object') return true;
  const saved = receipt as { revision?: unknown; shownAt?: unknown };
  return saved.revision !== revision || typeof saved.shownAt !== 'number' || !Number.isFinite(saved.shownAt)
    || now < saved.shownAt || now - saved.shownAt >= POPUP_INTERVAL_MS;
}
