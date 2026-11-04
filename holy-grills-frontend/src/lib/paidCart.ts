import { sessionStore } from './storage';
import { liveApi } from './liveApi';
import { clearPaidCheckout } from './guestOrders';

const KEY = 'hg_paid_cart_snapshots';
const read = () => {
  try { const value = JSON.parse(sessionStore.getItem(KEY) || '{}'); return value && typeof value === 'object' ? value : {}; }
  catch { return {}; }
};
const fingerprint = row => JSON.stringify([row.id, row.menu_item_id, row.quantity, row.selected_variations || [], row.selected_addons || [], row.notes || row.options?.notes || '']);

export function rememberPaymentCart(order, items) {
  if (!order?.user_id || order.payment_status !== 'pending' || !items?.length) return;
  const snapshots = read();
  // An idempotent retry must retain the original cart, not newer edits.
  if (snapshots[order.id]) return;
  snapshots[order.id] = { user_id: order.user_id, rows: items.map(fingerprint) };
  sessionStore.setItem(KEY, JSON.stringify(Object.fromEntries(Object.entries(snapshots).slice(-10))));
}

const settling = new Map<string, Promise<boolean>>();
export function settlePaidCart(order): Promise<boolean> {
  clearPaidCheckout(order);
  if (!order?.user_id || !['paid', 'partially_refunded'].includes(order.payment_status)) return Promise.resolve(false);
  if (settling.has(order.id)) return settling.get(order.id)!;
  const run = async () => {
    const snapshot = read()[order.id];
    if (!snapshot || snapshot.user_id !== order.user_id) return false;
    const current = await liveApi.cart.get();
    const fingerprints = new Set(snapshot.rows);
    // Preserve new/edited rows when a customer returns from a delayed payment.
    for (const row of current?.items || []) {
      if (row.id && fingerprints.has(fingerprint(row))) await liveApi.cart.remove(row.id);
    }
    const snapshots = read(); delete snapshots[order.id];
    sessionStore.setItem(KEY, JSON.stringify(snapshots));
    return true;
  };
  const promise = run().finally(() => settling.delete(order.id));
  settling.set(order.id, promise);
  return promise;
}
