import { localStore, sessionStore } from './storage';

// Guest capabilities belong to this browser tab. Never enumerate other sessions
// or use the old shared-device history as proof of ownership.
const KEY = 'hg_guest_order_receipts';
const read = () => {
  try { const rows = JSON.parse(sessionStore.getItem(KEY) || '[]'); return Array.isArray(rows) ? rows : []; }
  catch { return []; }
};
export const guestOrders = () => read();
export const forgetGuestOrder = (id: string) => sessionStore.setItem(KEY, JSON.stringify(read().filter(row => row.id !== id)));
export const guestOrderToken = (id: string) => read().find(row => row.id === id)?.claim_token;
export function saveGuestOrder(order, claimToken = order?.claim_token, cartItems?) {
  if (!order?.id || !claimToken) return;
  const old = read().find(row => row.id === order.id);
  sessionStore.setItem(KEY, JSON.stringify([{
    ...old, id: order.id, claim_token: claimToken,
    ...(cartItems ? { cart_items: cartItems } : {}),
    payment_status: order.payment_status, campus_id: order.campus_id,
  }, ...read().filter(row => row.id !== order.id)].slice(0, 10)));
}

// A verified paid order removes only the exact cart rows submitted for it.
// New/edited rows and another campus's cart must survive a delayed callback.
export function settleGuestCart(order) {
  if (!order || order.user_id || !['paid', 'partially_refunded'].includes(order.payment_status)) return false;
  const receipt = read().find(row => row.id === order.id);
  if (!receipt?.cart_items) return false;
  let cart;
  try { cart = JSON.parse(localStore.getItem('hg_guest_cart') || '[]'); } catch { return false; }
  if (!Array.isArray(cart)) return false;
  const paidRows = new Set(receipt.cart_items.map(row => JSON.stringify(row)));
  localStore.setItem('hg_guest_cart', JSON.stringify(cart.filter(row => !paidRows.has(JSON.stringify(row)))));
  sessionStore.setItem(KEY, JSON.stringify(read().map(row => row.id === order.id ? { ...row, payment_status: order.payment_status, cart_items: undefined } : row)));
  return true;
}

export function paymentReturnToken(search: string, hash: string) {
  return new URLSearchParams(hash.replace(/^#/, '')).get('claim_token') || new URLSearchParams(search).get('claim_token');
}
