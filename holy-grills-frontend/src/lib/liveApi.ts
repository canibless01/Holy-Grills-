// HolyGrill Live API — drop-in replacement for mockApi that calls the real backend.
// Every method mirrors mockApi's signature so components only change their import.
// Base URL + JWT token handling live in ./apiClient. Verified against the live
// backend at https://holy-grills-backend.onrender.com/api (Aug 2026).
import { apiClient, ApiError, login as apiLogin, clearTokens, isAuthenticated, getToken, API_BASE_URL } from './apiClient';
import { getOrderCustomer } from './hgUtils';
import { hpTierName } from './valueText';
import type { MyChallengesEnvelope } from '@/types/challenges';
import type { SelectFreeSidePayload } from '@/types/free-sides';

// Many list endpoints wrap the array in a keyed object (e.g. { hostels: [...] },
// { departments: [...] }, { levels: [...] }). This pulls the array out so every
// admin list view receives a plain array and `.map()` never crashes.
// The backend often documents a `{ key: [...] }` envelope while the live route
// returns a bare array, so this accepts both. The *input* is `unknown` — the
// value came off the wire and nothing may be assumed about it — while the result
// defaults to `any[]` so the ~90 call sites keep compiling: typing the rows
// per-endpoint is a per-call-site job, and a call site that knows its shape can
// now say `unwrap<Hostel>(res, 'hostels')` instead of casting.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
// Shared with the admin panel: the tier-name extraction lives in
// ./valueText (import-free, unit-tested) and is re-exported here so
// components can keep importing it from either module.
export { hpTierName } from './valueText';

const unwrap = <T = any>(res: unknown, ...keys: string[]): T[] => {
  if (Array.isArray(res)) return res as T[];
  if (res && typeof res === 'object') {
    const bag = res as Record<string, unknown>;
    for (const k of keys) {
      if (Array.isArray(bag[k])) return bag[k] as T[];
    }
  }
  return [];
};

// Endpoints documented in the API guide but NOT implemented on the live backend
// (verified 404). Reads degrade to an empty list so panels render an honest empty
// state; writes fail loudly so an action is never silently dropped.
const naList = () => [];
const naWrite = (method) => () => {
  throw new ApiError(404, `${method} — not implemented on the live backend yet`);
};

// ========== AUTH ==========
const auth = {
  async login(body) {
    const data = await apiLogin(body.email, body.password);
    return data;
  },
  async me() { return apiClient.get('/auth/me'); },
  async register(body) { return apiClient.post('/auth/register', body); },
  async refresh() { return apiClient.post('/auth/refresh', { refresh_token: localStorage.getItem('hg_refresh_token') }); },
  async updateProfile(body) { return apiClient.patch('/auth/profile', body); },
  // Dedicated avatar upload — POST /auth/profile/photo { photo_url }. The
  // update_profile route does not accept photo_url, so the avatar must go
  // through here or it is silently dropped.
  async updateProfilePhoto(body) { return apiClient.post('/auth/profile/photo', body); },
  async changePassword(body) { return apiClient.post('/auth/change-password', body); },
  async logout() { const r = await apiClient.post('/auth/logout'); clearTokens(); return r; },
  async logoutAll() { const r = await apiClient.post('/auth/logout-all-devices'); clearTokens(); return r; },
  async deleteAccount(body) { const r = await apiClient.delete('/auth/account', body); clearTokens(); return r; },
  // Email-request step: POST /auth/reset-password { email } — sends the reset email.
  async resetPassword(body) { return apiClient.post('/auth/reset-password', body); },
  // Confirm step: POST /auth/reset-password/confirm { token, new_password } —
  // consumes the token from the reset email and sets the new password. This is
  // the custom-backend confirm endpoint (users live in
  // the custom backend, so a Base44 resetPassword call could never validate the
  // custom-backend token). Endpoint path needs backend verification.
  async confirmReset(body) { return apiClient.post('/auth/reset-password/confirm', body); },
  async verifyEmail(body) { return apiClient.post('/auth/verify-email', body); },
  async deviceToken(body) { return apiClient.post('/auth/device-token', body); },
  async getStreak() { return apiClient.get('/auth/streak'); },
  // Check-in history — no dedicated backend endpoint; the streak record from
  // GET /auth/streak carries week_progress with day-level statuses, so the
  // calendar falls back to the streak counter when this returns [].
  async getCheckinHistory() { return []; },
};

// ========== ADDRESSES ==========
const addresses = {
  async list() { return apiClient.get('/auth/addresses'); },
  async create(body) { return apiClient.post('/auth/addresses', body); },
  async update(id, body) { return apiClient.patch(`/auth/addresses/${id}`, body); },
  async delete(id) { return apiClient.delete(`/auth/addresses/${id}`); },
};

// ========== MENU ==========
const menu = {
  async getItems(params = {}) { return apiClient.get('/menu/items', params); },
  async getItem(id) { return apiClient.get(`/menu/items/${id}`); },
  async getAddons(id) { return apiClient.get(`/menu/items/${id}/addons`); },
  async getCategories() { return apiClient.get('/menu/categories'); },
  async getGlobalAddons() { return apiClient.get('/menu/addons'); },
  async getKitchenCapacity() { return apiClient.get('/menu/kitchen-capacity'); },
};

// ========== CART ==========
const cart = {
  async get() { return apiClient.get('/cart'); },
  async add(body) { return apiClient.post('/cart', body); },
  async update(itemId, body) { return apiClient.patch(`/cart/${itemId}`, body); },
  async remove(itemId) { return apiClient.delete(`/cart/${itemId}`); },
  async clear() { return apiClient.delete('/cart'); },
};

// ========== ORDERS ==========
// Normalise a live order to the shape the student pages expect
// (order_items[].name_snapshot / delivery_address.line1 / delivery_window.label).
const normOrder = (o) => {
  if (!o) return o;
  const items = (o.order_items || o.items || []).map((it) => ({
    ...it,
    name_snapshot: it.name_snapshot || it.name,
    quantity: it.quantity || 1,
    line_total: it.line_total ?? (it.unit_price || it.price || 0) * (it.quantity || 1),
  }));
  return {
    ...o,
    order_items: items,
    items,
    delivery_address: o.delivery_address || (o.delivery_location ? { line1: typeof o.delivery_location === 'string' ? o.delivery_location : o.delivery_location.name } : { line1: '' }),
    delivery_window: o.delivery_window || (Array.isArray(o.delivery_windows) ? o.delivery_windows[0] : o.delivery_windows) || null,
    delivery_batch: o.delivery_batch || (Array.isArray(o.delivery_batches) ? o.delivery_batches[0] : o.delivery_batches) || null,
    total_amount: o.total_amount ?? o.total ?? 0,
  };
};
const orders = {
  async create(body) {
    const res = await apiClient.post('/orders', body);
    return normOrder(res?.order || res);
  },
  async list(params = {}) { return unwrap(await apiClient.get('/orders', params), 'orders'); },
  async get(id, params = {}) { return normOrder(await apiClient.get(`/orders/${id}`, params)); },
  async updateStatus(id, body) { return apiClient.patch(`/orders/${id}/status`, body); },
  async walk(id, body) { return apiClient.post(`/orders/${id}/walk`, body); },
  async cancel(id, body) { return apiClient.post(`/orders/${id}/cancel`, body); },
  async review(id, body) { return apiClient.post(`/orders/${id}/review`, body); },
  async validatePromo(body) { return apiClient.post('/orders/validate-promo', body); },
  async getDeliveryWindows() { return apiClient.get('/orders/delivery-windows'); },
  async getDeliveryWindowStatus() {
    const res = await apiClient.get('/orders/delivery-windows/status');
    // New kitchen-status contract — windows carry per-window delivery times and
    // slot counts (is_full/is_closed/remaining), and the closed case carries
    // the next opening date + time. Normalized additively so both the old
    // (active_window/message) and new (first_open_window/next_available_date)
    // consumers keep working.
    if (res && Array.isArray(res.windows) && res.windows.some((w) => w && (w.delivery_starts_at || w.is_full != null || w.is_closed != null))) {
      const openWindows = res.windows.filter((w) => w && !w.is_full && !w.is_closed);
      const first = openWindows[0] || null;
      // Trust the backend's is_open directly — the frontend must not recompute
      // it (the backend is the source of truth for kitchen open/closed).
      const isOpen = !!res.is_open;
      return {
        ...res,
        is_open: isOpen,
        any_capacity_remaining: res.any_capacity_remaining ?? openWindows.length > 0,
        first_open_window: isOpen ? first : null,
        active_window: isOpen ? { label: first.delivery_starts_at ? `Delivery ${first.delivery_starts_at}–${first.delivery_ends_at}` : 'ordering live' } : null,
        can_schedule: false,
        scheduled_windows: res.windows,
        available_windows: res.windows,
        next_window: null,
        message: isOpen
          ? `Order now — delivery between ${first.delivery_starts_at} and ${first.delivery_ends_at}${first.remaining != null ? ` · ${first.remaining} slots left` : ''}`
          : (res.next_available_date ? `Opens ${res.next_available_date} at ${res.next_opens_at || ''}`.trim() : 'Ordering is currently closed — check back soon.'),
      };
    }
    const windows = res.available_windows || res.windows || res.scheduled_windows || [];
    const open = windows.filter((w) => w.status === 'open');
    return {
      // Unknown stays unknown: when the backend does not state is_open, the
      // frontend must not derive it from window rows (that is a business call,
      // and checkout re-asks the backend anyway). `null` never opens the
      // "kitchen closed" popup — only an explicit false does.
      is_open: res.is_open ?? null,
      active_window: res.active_window || open[0] || null,
      can_schedule: res.can_schedule ?? true,
      scheduled_windows: res.scheduled_windows || windows,
      available_windows: windows,
      next_window: res.next_window || null,
      message: res.message || (res.is_open ? 'Ordering is open' : 'Ordering is currently closed. You can schedule for a future window.'),
    };
  },
  async reorder(id) { return apiClient.post(`/orders/${id}/reorder`); },
  async share(id, body) { return apiClient.post(`/orders/${id}/share`, body); },
  async addSquadMembers(id, body) { return apiClient.post(`/orders/${id}/squad-members`, body); },
  async refund(id, body) { return apiClient.post(`/orders/${id}/refund`, body); },
  async getHistory(id) { return apiClient.get(`/orders/${id}/history`); },
  // Guest order claiming — one-time link of a guest order to a registered account.
  async claim(id, body) { return apiClient.post(`/orders/${id}/claim`, body); },
  // F5 GAP (reported): the order page had a "resend tracking email" button calling
  // POST /orders/<id>/resend-tracking — orders.py exposes NO tracking route (no
  // /orders/*/tracking, no guest tracking link). The button is removed so the UI
  // stops promising an email it can never send. Restore both once the route exists.
  // Active orders only — dedicated endpoint (orders.py /api/orders/active).
  async getActive() { const res = await apiClient.get('/orders/active'); return res?.order ?? null; },
  // Cancel a scheduled (future-window) order — DELETE /api/orders/{id}/scheduled.
  async cancelScheduled(id) { return apiClient.delete(`/orders/${id}/scheduled`); },
  // Scheduled orders — GET /orders/scheduled → { scheduled_orders, count }
  async getScheduled() { const res = await apiClient.get('/orders/scheduled'); return { scheduled_orders: res?.scheduled_orders || [], count: res?.count ?? 0 }; },
  // Delivery zones — GET /orders/delivery-zones (public, bare array of zones with fees + ETA)
  async getDeliveryZones() { return unwrap(await apiClient.get('/orders/delivery-zones'), 'zones'); },
  // Review images — POST /orders/<id>/review/images { image_urls } (attaches to the existing review row)
  async addReviewImages(id, body) { return apiClient.post(`/orders/${id}/review/images`, body); },
  // Assigned rider call link — GET /orders/<id>/call-rider → { rider: { name, call_link } }
  async callRider(id) { return apiClient.get(`/orders/${id}/call-rider`); },
  // Stage 14 — one-tap reorder suggestion built from the last order.
  // { suggestion: { order_id, ordered_at, items: [{ name, quantity }] } } | { suggestion: null }
  async getSuggestion() { return apiClient.get('/orders/suggestions'); },
  // Per-order squad member management — order-scoped, the squad roster is untouched.
  async getSquadMembers(id) { return unwrap(await apiClient.get(`/orders/${id}/squad-members`), 'members', 'squad_members'); },
  async removeSquadMember(id, memberId) { return apiClient.delete(`/orders/${id}/squad-members/${memberId}`); },
  async resendSquadMemberInvite(id, memberId) { return apiClient.post(`/orders/${id}/squad-members/${memberId}/resend`); },
};

// ========== EVENTS ==========
const events = {
  async list() { return apiClient.get('/events'); },
  async get(id) { return apiClient.get(`/events/${id}`); },
  async register(id, body) { return apiClient.post(`/events/${id}/register`, body); },
  async checkin(id, body) { return apiClient.post(`/events/${id}/checkin`, body); },
  async generateQR(id) { return apiClient.post(`/events/${id}/qr`); },
  async cateringRequest(body) { return apiClient.post('/events/catering-requests', body); },
  async getTiers(id) { return unwrap(await apiClient.get(`/events/${id}/tiers`), 'tiers'); },
  // GET /events/my-tickets — the authenticated user's tickets, split into
  // upcoming / past / checked_in. Replaces the old event-detail `has_ticket`
  // probe (get_event returns no per-user ticket ownership field).
  async myTickets() { return apiClient.get('/events/my-tickets'); },
  // GET /events/<id>/tiers/comparison — enriched tiers with availability/sold-out.
  async getTierComparison(id) { return unwrap(await apiClient.get(`/events/${id}/tiers/comparison`), 'tiers'); },
  // GET /events/tiers/<tier_id>/detail — full tier + nested event.
  async getTierDetail(tierId) { return apiClient.get(`/events/tiers/${tierId}/detail`); },
  // GET /events/<id>/tickets/<ticket_id>/pdf — PDF ticket download (binary).
  // Ownership: for guest tickets the caller MUST pass guest_email as a query
  // param (spec §11.10). apiClient is JSON-only, so fetch the blob directly with
  // the same auth + campus headers and hand back an object URL for <a download>.
  async downloadTicketPdf(eventId, ticketId, guestEmail) {
    const token = getToken();
    const guestCampusId = !token && localStorage.getItem('hg_campus_id');
    const adminCampusId = token && localStorage.getItem('hg_admin_campus_id');
    const campusHeader = adminCampusId || guestCampusId;
    const qs = guestEmail ? `?guest_email=${encodeURIComponent(guestEmail)}` : '';
    const res = await fetch(`${API_BASE_URL}/events/${eventId}/tickets/${ticketId}/pdf${qs}`, {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(campusHeader ? { 'X-Campus-ID': campusHeader } : {}),
      },
    });
    if (!res.ok) throw new ApiError(res.status, 'Failed to download ticket PDF');
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  },
};

// ========== USERS (search) ==========
// Student-accessible user search — same-campus only, excludes the searcher.
// Used by the HP transfer recipient picker.
const users = {
  async search(params = {}) {
    const res = await apiClient.get('/users/search', params);
    return res?.results ?? res ?? [];
  },
};

// ========== HP ==========
const hp = {
  async getBalance() { return apiClient.get('/hp/balance'); },
  async getTransactions(params = {}) { return apiClient.get('/hp/transactions', params); },
  async getTiers() { return apiClient.get('/hp/tiers'); },
  async transfer(body) { return apiClient.post('/hp/transfer', body); },
  async flashRedeem(rewardId) { return apiClient.post(`/hp/flash-redeem/${rewardId}`); },
  async getUnlockHistory(params = {}) { return unwrap(await apiClient.get('/hp/unlock-history', params), 'unlocks', 'history'); },
  // HP bundles (event hosts buy HP for event rewards) — GET /hp/bundles, POST /hp/bundles/purchase.
  async getBundles() { return apiClient.get('/hp/bundles'); },
  async purchaseBundle(body) { return apiClient.post('/hp/bundles/purchase', body); },
  // Exclusive Spin — the leaderboard spin. Top earners get free spins (30-day
  // expiry); the prizes are the exclusive gift set (free items, HP jackpots,
  // Double-HP badge). There is no buy-extra-spin option.
  // Exclusive Spin blueprint is mounted at /exclusive-spin (NOT /hp/exclusive-spin).
  // GET  /exclusive-spin      → { total_spins, spins[], prizes[] }
  // POST /exclusive-spin/spin → { message, prize, spins_remaining }
  async getExclusiveSpinStatus() {
    const res = await apiClient.get('/exclusive-spin');
    // Normalize across possible backend response shapes so every surface
    // (rewards, leaderboard, profile) reads one key: total_spins.
    const s = res?.data ?? res ?? {};
    const list = Array.isArray(s.spins) ? s.spins : null;
    const count = s.total_spins ?? s.spins_available ?? s.spins_remaining ?? s.available_spins ?? s.remaining_spins
      ?? (list ? list.filter((x) => !x?.used_at && !x?.is_used).length : 0);
    return { ...s, total_spins: Number(count) || 0 };
  },
  async exclusiveSpin() { return apiClient.post('/exclusive-spin/spin'); },
};

// ========== REWARDS ==========
const rewards = {
  async list(params = {}) { return apiClient.get('/rewards', params); },
  async redeem(rewardId) { return apiClient.post(`/rewards/${rewardId}/redeem`); },
  async getRedemptions() { return apiClient.get('/rewards/redemptions'); },
  // Single reward detail — GET /rewards/<id> (public)
  async getReward(id) { return apiClient.get(`/rewards/${id}`); },
  // Delivery choice — POST /rewards/redemptions/:id/delivery-choice.
  // Backend records how a FULFILLED reward is received: 'instant' returns
  // { delivery_mode, next_step: 'checkout', reward_redemption_id } (the user
  // then checks out); 'next_order' returns { delivery_mode, message }. There is
  // no /checkout route on the rewards blueprint — the old call 404'd.
  async chooseDelivery(redemptionId, body) { return apiClient.post(`/rewards/redemptions/${redemptionId}/delivery-choice`, body); },
  // Free side credits — count + 60-day expiry shown in Profile / Rewards Dashboard,
  // decremented server-side when a free side is spent at checkout.
  // Free sides blueprint is mounted at /free-sides (NOT /rewards/free-side-credits).
  // GET /free-sides → { total_credits, credits[], available_sides[] }.
  // Normalise to the { count, expires_at } shape the Rewards dashboard reads.
  async getFreeSideCredits() {
    const res = await apiClient.get('/free-sides');
    const credits = Array.isArray(res?.credits) ? res.credits : [];
    const soonest = credits.map((c) => c.expires_at).filter(Boolean).sort()[0] || null;
    return {
      count: res?.total_credits ?? 0,
      expires_at: soonest,
      credits,
      available_sides: Array.isArray(res?.available_sides) ? res.available_sides : [],
    };
  },
  // F5: `redeemFreeSide` was deleted. The backend replaced the post-order
  // /free-sides/redeem flow with cart-stage selection — and selection is what
  // actually spends the credit (order_service consumes cart_free_side_selections
  // at order creation and inserts the ₦0 line). Checkout now selects/deselects
  // through these two methods instead of sending order-body fields the backend
  // ignored (docs/WIRING_AUDIT.md §3.1).
  async selectFreeSide(body: SelectFreeSidePayload) { return apiClient.post('/free-sides/select', body); },
  async deselectFreeSide(selectionId: string | number) { return apiClient.delete(`/free-sides/select/${selectionId}`); },
};

// ========== MARKETPLACE ==========
const marketplace = {
  async list(params = {}) { return apiClient.get('/marketplace', params); },
  async get(id) { return apiClient.get(`/marketplace/${id}`); },
  async purchase(listingId, body) { return apiClient.post(`/marketplace/${listingId}/purchase`, body); },
  async myPurchases(params = {}) { return unwrap(await apiClient.get('/marketplace/purchases', params), 'purchases'); },
  // Student "request a product" — POST /marketplace/requests (marketplace.py).
  async request(body) { return apiClient.post('/marketplace/requests', body); },
  // Report a delivered access code that doesn't work — POST /marketplace/purchases/<id>/report { reason }.
  // Returns { message, report }. Reason must be 5–500 chars (validated server-side).
  async reportPurchaseProblem(purchaseId, body) { return apiClient.post(`/marketplace/purchases/${purchaseId}/report`, body); },
};

// ========== WALLET ==========
// Backend wallet routes (wallet.py): GET /wallet, POST /wallet/fund/card,
// POST /wallet/fund/bank, GET /wallet/transactions, GET /wallet/admin/transactions.
// There is NO /wallet/withdraw or /wallet/verify/<ref> route on the backend —
// card funding returns a Paystack authorization_url and the Wallet page simply
// refreshes the balance on return, so those former methods were removed.
const wallet = {
  async get() { return apiClient.get('/wallet'); },
  async fundCard(body) { return apiClient.post('/wallet/fund/card', body); },
  async fundBank(body) { return apiClient.post('/wallet/fund/bank', body); },
  async getTransactions(params = {}) { return apiClient.get('/wallet/transactions', params); },
};

// ========== REFERRALS ==========
// /api/referrals returns the authenticated user's referral stats + list;
// /api/referrals/stats is the lightweight summary. Response shapes are
// normalised defensively so the page reads real backend values and falls
// back to an honest empty state when a field is absent.
const referrals = {
  async getStats() { return apiClient.get('/referrals/stats'); },
  async getHistory() {
    const r = await apiClient.get('/referrals');
    if (Array.isArray(r)) return r;
    if (r && Array.isArray(r.referrals)) return r.referrals;
    if (r && Array.isArray(r.history)) return r.history;
    if (r && Array.isArray(r.friends)) return r.friends;
    if (r && r.data && Array.isArray(r.data.referrals)) return r.data.referrals;
    return [];
  },
};

// ========== NOTIFICATIONS ==========
// Backend (notifications.py): GET /notifications → { notifications, unread_count }.
// Preferences: GET returns defaults if no row exists; PATCH only accepts the 6
// allowed boolean keys (push_enabled, email_enabled, order_updates, promotions,
// hp_updates, delivery_updates) — any other key is silently dropped server-side.
// Blasts: GET /notifications/blasts → { blasts, count }; POST returns
// { blast, sent_to } (immediate) or { blast, message } (scheduled).
const notifications = {
  async list(params = {}) { return apiClient.get('/notifications', params); },
  async markRead(id) { return apiClient.post(`/notifications/${id}/read`); },
  async markAllRead() { return apiClient.post('/notifications/read-all'); },
  async getPreferences() { return apiClient.get('/notifications/preferences'); },
  async updatePreferences(body) { return apiClient.patch('/notifications/preferences', body); },
};

// ========== PUSH (Web Push) ==========
// Backend (notifications.py push_bp, mounted at /api/push): POST /push/subscribe
// stores a browser Web Push subscription object { endpoint, keys: { p256dh, auth } }
// in push_subscriptions. DELETE /push/subscribe deactivates (optionally one endpoint).
// This is the native browser Push API — separate from the OneSignal device-token
// flow at /auth/device-token. Both coexist; the notification service sends via
// whichever subscription a device has.
const push = {
  async subscribe(body) { return apiClient.post('/push/subscribe', body); },
  async unsubscribe(body) { return apiClient.delete('/push/subscribe', body); },
};

// ========== LEADERBOARD ==========
const leaderboard = {
  async get(params = {}) { return apiClient.get('/leaderboard', params); },
  async getMyRank(params = {}) { return apiClient.get('/leaderboard/my-rank', params); },
  async getSquad(params = {}) { return apiClient.get('/leaderboard/squad', params); },
  async getHallOfFame() { return apiClient.get('/leaderboard/hall-of-fame'); },
  // Enriched inductee list (photo/faculty/department) — GET /leaderboard/hall-of-fame/inductees.
  async getInductees() { return unwrap(await apiClient.get('/leaderboard/hall-of-fame/inductees'), 'inductees', 'winners', 'hall_of_fame'); },
  // Shareable Hall of Fame inductee card — GET /leaderboard/hall-of-fame/inductees/{id}/card.
  async getHallOfFameCard(id) { return apiClient.get(`/leaderboard/hall-of-fame/inductees/${id}/card`); },
  // Authed user's squad ranks — GET /leaderboard/squad/my-rank.
  async getSquadMyRank(params = {}) { return apiClient.get('/leaderboard/squad/my-rank', params); },
};

// Normalise a kitchen order's item list to the shape the Kitchen panel expects
// (it reads order.order_items[].name_snapshot / received_at / delivery_windows.label).
const normKitchenOrder = (o) => {
  const c = getOrderCustomer(o);
  return {
    ...o,
    order_items: (o.order_items || o.items || []).map((it) => ({ ...it, name_snapshot: it.name_snapshot || it.name, quantity: it.quantity || 1 })),
    received_at: o.received_at || o.created_at,
    delivery_windows: o.delivery_windows || o.delivery_window,
    customer_name: c.display,
    customer_phone: c.phone,
  };
};

// ========== KITCHEN ==========
const kitchen = {
  // /kitchen/queue may return a flat array, a {received, preparing, ready} status
  // map, or an explicit wrapper ({orders|queue|data|items: [...]}). Flatten all
  // of them to a plain array. As a safety net we also pull /orders/active and
  // merge any kitchen-relevant orders (received/preparing/ready) that the queue
  // endpoint missed — this is the fix for the bug where a freshly placed order
  // showed on Admin but never reached the Kitchen queue.
  async getQueue(params = {}) {
    let arr = [];
    try {
      const res = await apiClient.get('/kitchen/queue', params);
      if (Array.isArray(res)) {
        arr = res;
      } else if (res && typeof res === 'object') {
        for (const k of ['orders', 'queue', 'data', 'items']) {
          if (Array.isArray(res[k])) arr = arr.concat(res[k].map((o) => ({ ...o, status: o.status || 'received' })));
        }
        if (!arr.length) {
          for (const status of Object.keys(res)) {
            if (Array.isArray(res[status])) arr = arr.concat(res[status].map((o) => ({ ...o, status: o.status || status })));
          }
        }
      }
    } catch (e) { arr = []; }

    // Fallback merge — active orders the queue endpoint may have missed.
    const kitchenStatuses = ['received', 'preparing', 'ready'];
    try {
      let active = await apiClient.get('/orders/active');
      if (active && !Array.isArray(active)) active = active.orders || active.active_orders || [];
      active = (active || []).filter((o) => kitchenStatuses.includes(o.status));
      // Kitchen queue wins on conflicts; active fills any gaps.
      const byId = new Map();
      for (const o of active) byId.set(o.id, o);
      for (const o of arr) byId.set(o.id, o);
      arr = Array.from(byId.values());
    } catch (e) { /* active endpoint unavailable — keep queue result */ }

    const rank = { received: 0, preparing: 1, ready: 2 };
    arr.sort((a, b) => (rank[a.status] ?? 9) - (rank[b.status] ?? 9) || Number(new Date(a.received_at || a.created_at)) - Number(new Date(b.received_at || b.created_at)));
    return arr.map(normKitchenOrder);
  },
  async getScheduled() {
    const res = await apiClient.get('/kitchen/scheduled');
    if (Array.isArray(res)) return { count: res.length, scheduled_orders: res.map(normKitchenOrder) };
    if (res && Array.isArray(res.scheduled_orders)) return { ...res, scheduled_orders: res.scheduled_orders.map(normKitchenOrder) };
    if (res && Array.isArray(res.orders)) return { count: res.count ?? res.orders.length, scheduled_orders: res.orders.map(normKitchenOrder) };
    return { count: 0, scheduled_orders: [] };
  },
  async getBatchSummary(windowId) {
    const res = await apiClient.get(`/kitchen/batch-summary/${windowId}`);
    if (res && Array.isArray(res.summary)) return res;
    if (res && Array.isArray(res.items)) return { total_orders: res.total_orders ?? res.items.length, summary: res.items.map((i) => ({ item_name: i.item_name || i.name, total_quantity: i.total_quantity || i.quantity || 0 })) };
    return { total_orders: (res && res.total_orders) || 0, summary: (res && res.summary) || [] };
  },
  async getMetrics() { return apiClient.get('/kitchen/metrics'); },
  async getWindows() { return unwrap(await apiClient.get('/kitchen/windows'), 'windows'); },
  // GET /kitchen/settings → { settings: {key: value}, updated_at: {key: ts} }
  // The backend stores settings as arbitrary key/value strings. Return the
  // settings map as a flat object — values are strings (the backend does
  // str(value) on upsert). Consumers parse booleans/numbers as needed.
  async getSettings() {
    const res = await apiClient.get('/kitchen/settings');
    return (res && res.settings) ? res.settings : {};
  },
  // PATCH /kitchen/settings expects { settings: {key: value, ...} }.
  async updateSettings(settingsMap) { return apiClient.patch('/kitchen/settings', { settings: settingsMap }); },
  async batchAdvanceStatus(windowId, body) { return apiClient.post(`/kitchen/batch/${windowId}/advance`, body); },
  async markItemUnavailable(itemId) { return apiClient.patch(`/menu/items/${itemId}`, { is_available: false, is_sold_out: true }); },
  async markItemAvailable(itemId) { return apiClient.patch(`/menu/items/${itemId}`, { is_available: true, is_sold_out: false }); },
};

// ========== RIDERS ==========
const riders = {
  async getMyBatch() {
    const res = await apiClient.get('/riders/my-batch');
    // Already panel shape { batch, orders, ... } — preserve any extra keys the
    // backend added (other_batches, sequencing_mode) so the rider UI can surface
    // upcoming batches and the sequencing policy.
    if (res && res.batch) return res;
    // Flat live shape: { batch_id, zone, status, delivery_window, orders, ... }
    const orders = (res && res.orders ? res.orders : []).map((o) => {
      const cust = getOrderCustomer(o);
      return {
      ...o,
      id: o.id || o.order_id,
      customer_name: cust.display,
      customer_phone: cust.phone,
      customer_email: cust.email,
      delivery_address: typeof o.delivery_address === 'string'
        ? o.delivery_address
        : [o.delivery_address && o.delivery_address.hostel, o.delivery_address && o.delivery_address.room].filter(Boolean).join(' ') || o.delivery_location || '',
      items: (o.items || o.order_items || []).map((it) => ({ ...it, name_snapshot: it.name_snapshot || it.name })),
      distance_km: o.distance_km ?? '',
      delivery_rank: o.delivery_rank ?? '',
      delivery_hint: o.delivery_hint || o.notes || '',
      };
    });
    return {
      batch: {
        id: (res && (res.batch_id || res.id)) || '',
        zone: res && res.zone,
        status: res && res.status,
        delivery_window: res && res.delivery_window,
        rider_pay_total: res && res.rider_pay_total,
        rider_paid_at: res && res.rider_paid_at,
      },
      orders,
      other_batches: (res && res.other_batches) || [],
      sequencing_mode: (res && res.sequencing_mode) || 'single',
    };
  },
  async pickup(orderId) { return apiClient.post(`/riders/orders/${orderId}/pickup`); },
  async deliver(orderId) { return apiClient.post(`/riders/orders/${orderId}/deliver`); },
  async attempt(orderId, body) { return apiClient.post(`/riders/orders/${orderId}/attempt`, body); },
  async setAvailability(body) { return apiClient.patch('/riders/availability', body); },
  // Rider earnings — hg_rider_earnings returns:
  // { rider_id, total_earnings, total_paid, outstanding, completed_batches,
  //   total_batches, unpriced_batches, batches: [{ id, order_count, batch_pay,
  //     rider_pay_total, rider_paid_at, delivered_at, zone }] }
  // The old code mapped to total_deliveries/deliveries which never existed on the
  // backend, so the Earnings tab always read 0 / empty.
  async getEarnings(params = {}) {
    const res = await apiClient.get('/riders/earnings', params);
    if (Array.isArray(res)) return { total_earnings: 0, completed_batches: 0, batches: [] };
    return {
      total_earnings: res?.total_earnings ?? 0,
      total_paid: res?.total_paid ?? 0,
      outstanding: res?.outstanding ?? 0,
      completed_batches: res?.completed_batches ?? 0,
      total_batches: res?.total_batches ?? 0,
      unpriced_batches: res?.unpriced_batches ?? 0,
      batches: Array.isArray(res?.batches) ? res.batches : [],
      ...(res || {}),
    };
  },
  async getStats() {
    // Spec §6.7: { rider_id, total_batches, completed_batches, completion_rate (0-100),
    // total_orders_delivered, zones_served[], is_available, availability_updated_at }.
    const res = await apiClient.get('/riders/stats');
    if (!res) return {};
    return {
      total_batches: res.total_batches ?? 0,
      completed_batches: res.completed_batches ?? 0,
      completion_rate: Number(res.completion_rate ?? 0),
      total_orders_delivered: res.total_orders_delivered ?? 0,
      zones_served: Array.isArray(res.zones_served) ? res.zones_served : [],
      is_available: res.is_available ?? false,
      availability_updated_at: res.availability_updated_at ?? null,
      ...(res || {}),
    };
  },
  async getHistory() { return unwrap(await apiClient.get('/riders/history'), 'deliveries', 'history'); },
  async getCallLink(orderId) {
    const res = await apiClient.get(`/riders/call/${orderId}`);
    return { call_link: (res && (res.call_link || res.call_url || res.callLink)) || '', ...(res || {}) };
  },
  async batchDeliver(body) {
    // No batch endpoint — deliver each order individually
    const ids = body.order_ids || [];
    const results = await Promise.allSettled(ids.map(id => apiClient.post(`/riders/orders/${id}/deliver`)));
    return { message: 'Batch delivery confirmed', delivered_count: results.filter(r => r.status === 'fulfilled').length };
  },
  // Rider live tracking — POST /riders/location-update { lat, lng }.
  // Called on an interval while the rider is online + has an active batch.
  async locationUpdate(body) { return apiClient.post('/riders/location-update', body); },
};

// ========== ANALYTICS ==========
// Pass-through — the exact response shapes are admin-only (401 without an admin
// token) and could not be verified. AdminDashboard guards every field so it
// renders live values where the shape matches and degrades gracefully otherwise.
const analytics = {
  async dashboard(params = {}) { return apiClient.get('/analytics/dashboard', params); },
  async sales(params = {}) { return apiClient.get('/analytics/sales', params); },
  async orders(params = {}) { return apiClient.get('/analytics/orders', params); },
  async items(params = {}) { return apiClient.get('/analytics/items', params); },
  async users(params = {}) { return apiClient.get('/analytics/users', params); },
  async retention(params = {}) { return apiClient.get('/analytics/retention', params); },
  // First-order gift status breakdown (analytics.py gifts_analytics).
  async gifts(params = {}) { return apiClient.get('/analytics/gifts', params); },
  // Marketplace analytics — purchases + code inventory status.
  async marketplace(params = {}) { return apiClient.get('/analytics/marketplace', params); },
  // Abandoned cart analytics — total / recovered / unrecovered counts.
  async abandonedCarts(params = {}) { return apiClient.get('/analytics/abandoned-carts', params); },
  // New dashboards (spec Section 4) — each is a single GET, read-only.
  async orderTiming(params = {}) { return apiClient.get('/analytics/order-timing', params); },
  async addonAcceptance(params = {}) { return apiClient.get('/analytics/addon-acceptance', params); },
  async deliveryLocations(params = {}) { return apiClient.get('/analytics/delivery-locations', params); },
  async squadOrders(params = {}) { return apiClient.get('/analytics/squad-orders', params); },
  async demographics(params = {}) { return apiClient.get('/analytics/demographics', params); },
  async engagement(params = {}) { return apiClient.get('/analytics/engagement', params); },
  async paymentMethods(params = {}) { return apiClient.get('/analytics/payment-methods', params); },
  async revenue(params = {}) { return apiClient.get('/analytics/revenue', params); },
  // B1 — Academic Calendar: order volume during exam/semester periods vs normal days.
  async academicCalendar(params = {}) { return apiClient.get('/analytics/academic-calendar', params); },
  // B2 — Order Sources: breakdown by channel (website, whatsapp, instagram, referral, sms, other).
  async orderSources(params = {}) { return apiClient.get('/analytics/order-sources', params); },
  // A9 — Referral Network: top referrers driving new signups.
  async referralNetwork(params = {}) { return apiClient.get('/analytics/referral-network', params); },
  // A8 — Retention & LTV: repeat order rate and customer LTV.
  async retentionLtv(params = {}) { return apiClient.get('/analytics/retention-ltv', params); },
  // B4 — Brand Partnerships: log/list/update brand data-sharing requests.
  async getBrandPartnerships() { return unwrap(await apiClient.get('/analytics/brand-partnerships'), 'brand_partnerships'); },
  async createBrandPartnership(body) { return apiClient.post('/analytics/brand-partnerships', body); },
  async updateBrandPartnership(id, body) { return apiClient.patch(`/analytics/brand-partnerships/${id}`, body); },
};

// ========== ADMIN ==========
const admin = {
  // --- Campuses (Domain 0 — super-admin cross-campus management) ---
  async getCampuses() { return unwrap(await apiClient.get('/admin/campuses'), 'campuses'); },

  // --- Archived menu items ---
  // F5 GAP (reported): GET /items/archived has no backend route — menu.py filters
  // on is_archived but never lists archived rows. The AdminMenu "Archived" view was
  // removed rather than left rendering an empty list forever; the rows are still in
  // the database when the route is added.

  // --- Admin webhook history (GET /admin/webhook-events) ---
  // Route supports provider, status, from_date, to_date, campus_id, limit, offset.
  async getWebhookEvents(params = {}) { return unwrap(await apiClient.get('/admin/webhook-events', params), 'events', 'webhook_events'); },

  // --- Academic Calendar (POST / GET / PATCH /:id under /admin/academic-calendar) ---
  // campus_id optional — omit for a platform-wide period (e.g. national holiday).
  async getAcademicCalendar() { return unwrap(await apiClient.get('/admin/academic-calendar'), 'academic_calendar', 'periods', 'calendar', 'entries'); },
  async createAcademicCalendar(body) { return apiClient.post('/admin/academic-calendar', body); },
  async updateAcademicCalendar(id, body) { return apiClient.patch(`/admin/academic-calendar/${id}`, body); },

  // --- Users (verified: /admin/users, /admin/users/:id, role/deactivate/activate, hp, wallet, orders) ---
  async getUsers(params = {}) { return unwrap(await apiClient.get('/admin/users', params), 'users'); },
  async getUser(userId) { return apiClient.get(`/admin/users/${userId}`); },
  async updateRole(userId, body) { return apiClient.patch(`/admin/users/${userId}/role`, body); },
  async deactivateUser(userId) { return apiClient.post(`/admin/users/${userId}/deactivate`); },
  async activateUser(userId) { return apiClient.post(`/admin/users/${userId}/activate`); },
  async getUserHp(userId) {
    const r = await apiClient.get(`/admin/users/${userId}/hp`);
    const tx = Array.isArray(r?.transactions) ? r.transactions : Array.isArray(r?.hp_transactions) ? r.hp_transactions : Array.isArray(r?.history) ? r.history : Array.isArray(r?.ledger) ? r.ledger : [];
    // The backend wraps the balance dict in `hp_balance` (from get_hp_balance).
    // Drill into it so total/active/pending read the real numbers, not the dict.
    const b = (r?.hp_balance && typeof r.hp_balance === 'object' && !Array.isArray(r.hp_balance)) ? r.hp_balance : r;
    return {
      // get_hp_balance() names the combined figure `total_visible`
      // (active + pending); `total` is not a field it returns, so it has to
      // be read here or the drawer always shows 0.
      total: b?.total ?? b?.total_visible ?? b?.balance ?? b?.active_balance ?? b?.total_hp ?? r?.total ?? 0,
      active: b?.active ?? b?.active_hp ?? b?.active_balance ?? r?.active ?? 0,
      pending: b?.pending ?? b?.pending_hp ?? b?.pending_hp_balance ?? b?.reserved ?? r?.pending ?? 0,
      // get_hp_balance() nests the tier row one level deep
      //   { tier: { tier: {name: 'Flame', ...}, is_in_grace_period: false } }
      // while /admin/users/:id returns the same shape at the top level.
      // Handing either dict to a component renders it as a React child, which
      // is what crashed the user drawer — so flatten to a display string here.
      tier: hpTierName(r?.tier) ?? hpTierName(b?.tier) ?? null,
      // The balance dict calls the earn rate `tier_bonus_multiplier`.
      tier_multiplier: r?.tier_multiplier ?? b?.tier_bonus_multiplier ?? b?.tier_multiplier ?? null,
      hp_earned_120day: b?.hp_earned_120day ?? r?.hp_earned_120day ?? null,
      degraded: !!(b?.degraded ?? r?.degraded),
      transactions: tx,
    };
  },
  async getUserWallet(userId) { return apiClient.get(`/admin/users/${userId}/wallet`); },
  async getUserOrders(userId, params = {}) { return unwrap(await apiClient.get(`/admin/users/${userId}/orders`, params), 'orders'); },
  async bulkGrantHp(body) { return apiClient.post('/admin/hp/bulk-grant', body); },
  async getHpReport() { return apiClient.get('/admin/hp/report'); },
  async grantHpToUser(userId, body) { return apiClient.post('/hp/admin/grant', { user_id: userId, ...body }); },
  async expireHpFromUser(userId, body) { return apiClient.post('/hp/admin/expire', { user_id: userId, ...body }); },

  // --- Orders (verified: /admin/orders, /orders/:id/status, /orders/:id/refund, /orders/:id/history) ---
  async getAdminOrders(params = {}) { return unwrap(await apiClient.get('/admin/orders', params), 'orders'); },
  async overrideOrderStatus(id, body) { return apiClient.patch(`/orders/${id}/status`, body); },
  async refund(id, body) { return apiClient.post(`/orders/${id}/refund`, body); },
  async getOrderHistory(id) { return apiClient.get(`/orders/${id}/history`); },

  // --- Delivery Windows (verified: /admin/delivery-windows + close/reopen) ---
  async getDeliveryWindows() { return unwrap(await apiClient.get('/admin/delivery-windows'), 'windows', 'delivery_windows'); },
  async createDeliveryWindow(body) { return apiClient.post('/admin/delivery-windows', body); },
  async updateDeliveryWindow(id, body) { return apiClient.patch(`/admin/delivery-windows/${id}`, body); },
  async closeWindow(id) { return apiClient.post(`/admin/delivery-windows/${id}/close`); },
  async reopenWindow(id) { return apiClient.post(`/admin/delivery-windows/${id}/reopen`); },

  // --- Ordering Windows (GET/POST /admin/ordering-windows, PATCH /:id) ---
  // Capacity + open/close times per weekday or date; a capacity increase can
  // reassign deferred orders — handled server-side.
  async getOrderingWindows() { return unwrap(await apiClient.get('/admin/ordering-windows'), 'windows', 'ordering_windows'); },
  async createOrderingWindow(body) { return apiClient.post('/admin/ordering-windows', body); },
  async updateOrderingWindow(id, body) { return apiClient.patch(`/admin/ordering-windows/${id}`, body); },

  // --- Delivery Batches (verified: /admin/delivery-batches + /:id/orders) ---
  async getDeliveryBatches() { return unwrap(await apiClient.get('/admin/delivery-batches'), 'batches', 'delivery_batches'); },
  async createDeliveryBatch(body) { return apiClient.post('/admin/delivery-batches', body); },
  async updateDeliveryBatch(id, body) { return apiClient.patch(`/admin/delivery-batches/${id}`, body); },
  async deleteDeliveryBatch(id) { return apiClient.delete(`/admin/delivery-batches/${id}`); },
  async getDeliveryBatchOrders(id) { return unwrap(await apiClient.get(`/admin/delivery-batches/${id}/orders`), 'orders'); },

  // --- Rider management (riders.py /api/riders/admin/*) ---
  // Roster: GET /riders/roster → { riders: [{ rider_id, full_name, phone,
  //   campus_id, is_available, availability_updated_at, location_lat,
  //   location_lng, location_updated_at, active_batches }], count }.
  // Payments summary: GET /riders/admin/payments?period= → { riders: [...], count }
  //   (hg_admin_rider_payments RPC — rider_id, full_name, earnings/paid/outstanding).
  // Per-rider batches: GET /riders/admin/payments/<rider_id>?period= → { rider_id,
  //   batches: [...], count } (hg_admin_rider_batches RPC).
  // Set batch pay: PATCH /riders/admin/batches/<batch_id>/pay { rider_pay_total }.
  // Pay breakdown: GET /riders/admin/batches/<batch_id>/pay-breakdown → { batch_id,
  //   orders: [...], count }.
  // Mark paid/unpaid: POST /riders/admin/payments/mark-paid|mark-unpaid
  //   body { batch_ids: [...] } → { updated, skipped, not_found }.
  async getRiderRoster() { return unwrap(await apiClient.get('/riders/roster'), 'riders', 'roster'); },
  async getRiderPayments(params = {}) { return unwrap(await apiClient.get('/riders/admin/payments', params), 'riders', 'payments'); },
  async getRiderPaymentBatches(riderId, params = {}) { return apiClient.get(`/riders/admin/payments/${riderId}`, params); },
  async setBatchPay(batchId, body) { return apiClient.patch(`/riders/admin/batches/${batchId}/pay`, body); },
  async getBatchPayBreakdown(batchId) { return apiClient.get(`/riders/admin/batches/${batchId}/pay-breakdown`); },
  async markBatchesPaid(batchIds) { return apiClient.post('/riders/admin/payments/mark-paid', { batch_ids: Array.isArray(batchIds) ? batchIds : [batchIds] }); },
  async markBatchesUnpaid(batchIds) { return apiClient.post('/riders/admin/payments/mark-unpaid', { batch_ids: Array.isArray(batchIds) ? batchIds : [batchIds] }); },

  // --- Abandoned Carts (verified: /admin/abandoned-carts + /:id/nudge) ---
  async getAbandonedCarts() { return unwrap(await apiClient.get('/admin/abandoned-carts'), 'carts', 'abandoned_carts'); },
  async nudgeAbandonedCart(id) { return apiClient.post(`/admin/abandoned-carts/${id}/nudge`); },
  // --- Order Locks Admin (verified: /order-locks/admin/all) ---
  async getOrderLocks(params = {}) { return unwrap(await apiClient.get('/order-locks/admin/all', params), 'locks', 'order_locks'); },

  // --- Promo Codes (verified: /admin/promo-codes, /:id, /:id/uses) ---
  async getPromoCodes() { return unwrap(await apiClient.get('/admin/promo-codes'), 'promo_codes', 'codes'); },
  async createPromoCode(body) { return apiClient.post('/admin/promo-codes', body); },
  async updatePromoCode(id, body) { return apiClient.patch(`/admin/promo-codes/${id}`, body); },
  async togglePromoCode(id) {
    const codes = unwrap(await apiClient.get('/admin/promo-codes'), 'promo_codes', 'codes');
    const p = codes.find(c => c.id === id);
    if (!p) throw new ApiError(404, 'Promo code not found');
    return apiClient.patch(`/admin/promo-codes/${id}`, { is_active: !p.is_active });
  },
  // Backend returns { promo_code, total_uses, total_discount_given, uses }.
  // Return the full envelope so the UI can read the backend-owned totals
  // instead of recomputing them.
  async getPromoCodeUses(id) { return apiClient.get(`/admin/promo-codes/${id}/uses`); },

  // --- Audit Log & Cron (verified: /admin/audit-log, /admin/cron/status, /admin/cron/:job) ---
  async getAuditLog(params = {}) { return unwrap(await apiClient.get('/admin/audit-log', params), 'logs', 'audit_log', 'entries'); },
  async triggerCron(jobName) { return apiClient.post(`/admin/cron/${jobName}`); },
  async getCronStatus() {
    const { KNOWN_CRON_MAP } = await import('./cronJobs');
    const normalize = (list) => (list || []).map((j) => {
      const job = j.job || j.name || j.id;
      const known = job ? KNOWN_CRON_MAP[job] : null;
      return {
        job,
        status: j.status || (j.last_triggered ? 'ok' : 'never_run'),
        last_triggered: j.last_triggered || j.last_run || null,
        cadence: j.cadence || j.schedule || known?.cadence || '—',
        desc: j.desc || known?.desc || '',
        ...j,
      };
    });
    let backendJobs = [];
    const res = await apiClient.get('/admin/cron/status').catch(() => null);
    if (Array.isArray(res)) backendJobs = normalize(res);
    else if (res && Array.isArray(res.jobs)) backendJobs = normalize(res.jobs);
    else if (res && Array.isArray(res.cron_jobs)) backendJobs = normalize(res.cron_jobs);
    else if (res && res.jobs && typeof res.jobs === 'object' && !Array.isArray(res.jobs)) {
      // The live backend returns { checked_at, jobs: { "birthday-hp": {...}, ... }, summary }
      // — jobs is a dict keyed by job name, not an array.
      backendJobs = normalize(Object.entries(res.jobs).map(([job, info]) => {
        const o = (info && typeof info === 'object') ? info : { status: info };
        return { job, ...o };
      }));
    }
    else if (res && typeof res === 'object' && !Array.isArray(res)) {
      backendJobs = normalize(Object.entries(res).map(([job, info]) => {
        const o = (info && typeof info === 'object') ? info : { status: info };
        return { job, ...o };
      }));
    }
    // Merge: every known beat job appears even if the backend's status endpoint
    // doesn't report it. Backend-reported status/last_triggered wins.
    const seen = new Set(backendJobs.map((j) => j.job));
    const missing = Object.values(KNOWN_CRON_MAP)
      .filter((k) => !seen.has(k.job))
      .map((k) => ({ job: k.job, status: 'never_run', last_triggered: null, cadence: k.cadence, desc: k.desc }));
    return [...backendJobs, ...missing];
  },

  // --- Campus delivery area ---
  // The delivery radius is two values, not one, and neither had a UI:
  //   • the campus CENTRE POINT (campuses.lat / .lon) — PATCH /admin/campuses/:id/location,
  //     the single origin that `is_within_delivery_area` measures the radius from;
  //   • the RADIUS itself (kitchen_settings.max_delivery_radius_km) — PATCH /kitchen/settings,
  //     campus-scoped server-side by _resolve_kitchen_campus_id().
  async getCampusLocation(campusId) { return apiClient.get(`/admin/campuses/${campusId}/location`); },
  // body: { coordinates: "7.3021, 5.1391" } | { lat, lon } | { lat: null, lon: null } to clear.
  // Coordinates outside Nigeria are refused unless force: true.
  async setCampusLocation(campusId, body) { return apiClient.patch(`/admin/campuses/${campusId}/location`, body); },

  // --- System Settings (verified: /admin/settings, /admin/settings/:key) ---
  async getSystemSettings() { return unwrap(await apiClient.get('/admin/settings'), 'settings'); },
  async createSystemSetting(body) { return apiClient.post('/admin/settings', body); },
  async updateSystemSetting(key, body) { return apiClient.patch(`/admin/settings/${key}`, body); },
  // Gift settings — GET /admin/gifts/settings returns first_order_gift_enabled, launch_window_end_date, first_order_gift_item_name.
  // Phase 3 — path corrected: the backend serves settings at /admin/settings (admin_gifts.py:125), there is no /admin/gifts prefix.
  async getGiftSettings() { const res = await apiClient.get('/admin/settings'); return res && res.settings ? res.settings : (res || {}); },
  async updateGiftSetting(key, body) { return apiClient.patch(`/admin/settings/${key}`, body); },

  // --- Menu Categories (POST/PATCH/DELETE /menu/categories) ---
  // "Delete" is a soft-deactivate (is_active=false); PATCH with is_active=true reactivates.
  async createCategory(body) { return apiClient.post('/menu/categories', body); },
  async updateCategory(id, body) { return apiClient.patch(`/menu/categories/${id}`, body); },
  async deleteCategory(id) { return apiClient.delete(`/menu/categories/${id}`); },

  // --- Menu Items (verified: /menu/items, /menu/items/:id, archive, bulk-availability, kitchen-capacity) ---
  async getMenuItems(params = {}) { return unwrap(await apiClient.get('/menu/items', params), 'items'); },
  async createMenuItem(body) { return apiClient.post('/menu/items', body); },
  async updateMenuItem(id, body) { return apiClient.patch(`/menu/items/${id}`, body); },
  async toggleMenuItemAvailability(id) {
    const items = unwrap(await apiClient.get('/menu/items'), 'items');
    const item = items.find(i => i.id === id);
    if (!item) throw new ApiError(404, 'Item not found');
    return apiClient.patch(`/menu/items/${id}`, { is_available: !item.is_available, is_sold_out: !!item.is_available });
  },
  async deleteMenuItem(id) { return apiClient.post(`/menu/items/${id}/archive`); },
  async bulkToggleMenuItemAvailability(ids, is_available) {
    return apiClient.patch('/menu/items/bulk-availability', { item_ids: ids, is_available });
  },
  async updateMenuItemHpMultiplier(id, body) {
    return apiClient.patch(`/menu/items/${id}`, { hp_multiplier: body.multiplier });
  },
  async bulkUpdateMenuItemHpMultiplier(ids, multiplier) {
    const results = await Promise.allSettled(ids.map(id => apiClient.patch(`/menu/items/${id}`, { hp_multiplier: multiplier })));
    return { updated_count: results.filter(r => r.status === 'fulfilled').length };
  },
  async getMenuCapacitySettings() { return apiClient.get('/menu/kitchen-capacity'); },
  async updateMenuCapacitySettings(body) { return apiClient.patch('/menu/kitchen-capacity', body); },

  // --- Addons & Variations (verified: /menu/addons, /menu/items/:id/variation-groups(+options), /menu/items/:id/addon-groups) ---
  async getAddonsConfig() {
    const addons = await apiClient.get('/menu/addons');
    return { global_addons: unwrap(addons, 'addons', 'global_addons'), variation_groups: {}, addon_groups: {} };
  },
  async createGlobalAddon(body) { return apiClient.post('/menu/addons', body); },
  async updateGlobalAddon(id, body) { return apiClient.patch(`/menu/addons/${id}`, body); },
  async deleteGlobalAddon(id) { return apiClient.post(`/menu/addons/${id}/archive`); },
  // Per-item variation groups + addon groups with their individual options/addons.
  // The group create/update routes do NOT accept nested `options`/`addons` arrays,
  // so each option and addon must be CRUD'd through its own endpoint. For existing
  // groups the old options are deleted before recreating from the editor text —
  // the text-area editor loses option IDs, so a full replace is the only correct
  // strategy. Removed groups are deleted entirely.
  async saveItemModifiers(itemId, body) {
    const results = { variation_groups: [], addon_groups: [] };

    // Fetch current state so we can delete removed groups and stale options.
    let existingDetail = null, existingAddons = null;
    try {
      [existingDetail, existingAddons] = await Promise.all([
        apiClient.get(`/menu/items/${itemId}`),
        apiClient.get(`/menu/items/${itemId}/addons`),
      ]);
    } catch (e) { /* proceed without delete capability */ }

    const existingVarGroups = existingDetail?.variation_groups || [];
    const existingAddonGroups = existingAddons?.addon_groups || [];

    // Groups the user is keeping (real UUIDs only — temp IDs are new groups).
    const keptVarIds = new Set((body.variation_groups || []).filter((g) => g.id && !g.id.startsWith('vg_')).map((g) => g.id));
    const keptAddonIds = new Set((body.addon_groups || []).filter((g) => g.id && !g.id.startsWith('ag_')).map((g) => g.id));

    // Delete variation groups no longer in the editor.
    await Promise.all(existingVarGroups
      .filter((g) => !keptVarIds.has(g.id))
      .map((g) => apiClient.delete(`/menu/items/${itemId}/variation-groups/${g.id}`).catch(() => {})));

    // Delete addon groups no longer in the editor.
    await Promise.all(existingAddonGroups
      .filter((g) => !keptAddonIds.has(g.id))
      .map((g) => apiClient.delete(`/menu/items/${itemId}/addon-groups/${g.id}`).catch(() => {})));

    // ── Variation groups + their options ──
    for (const vg of (body.variation_groups || [])) {
      const groupPayload = {
        name: vg.name,
        is_required: !!vg.is_required,
        min_selections: vg.min_selections ?? (vg.is_required ? 1 : 0),
        max_selections: vg.max_selections ?? 1,
        sort_order: vg.sort_order ?? 0,
      };
      let groupId = vg.id;
      let oldOpts = [];
      if (vg.id && !vg.id.startsWith('vg_')) {
        // Existing group — update it; its options are reconciled below instead of
        // being wiped and recreated (that burned their UUIDs, so any order history
        // referencing an option pointed at a deleted row).
        await apiClient.patch(`/menu/items/${itemId}/variation-groups/${groupId}`, groupPayload);
        oldOpts = existingVarGroups.find((g) => g.id === groupId)?.options || [];
      } else {
        // New group.
        const created = await apiClient.post(`/menu/items/${itemId}/variation-groups`, groupPayload);
        groupId = created?.id;
      }
      // The editor's text field carries names, not ids, so options are matched to
      // existing rows by name: matches are PATCHed in place (route verified —
      // PATCH /menu/items/<id>/variation-groups/<gid>/options/<oid>), new names are
      // created, and options the admin removed are deleted.
      const keptOptIds = new Set();
      await Promise.all((vg.options || []).map((opt, i) => {
        const payload = {
          name: opt.name,
          price_delta: Number(opt.price_delta) || 0,
          is_available: opt.is_available !== false,
          sort_order: opt.sort_order ?? i,
        };
        const match = oldOpts.find((o) => o.name === opt.name && !keptOptIds.has(o.id));
        if (match) { keptOptIds.add(match.id); return apiClient.patch(`/menu/items/${itemId}/variation-groups/${groupId}/options/${match.id}`, payload).catch(() => {}); }
        return apiClient.post(`/menu/items/${itemId}/variation-groups/${groupId}/options`, payload).catch(() => {});
      }));
      await Promise.all(oldOpts
        .filter((o) => !keptOptIds.has(o.id))
        .map((o) => apiClient.delete(`/menu/items/${itemId}/variation-groups/${groupId}/options/${o.id}`).catch(() => {})));
      results.variation_groups.push({ id: groupId, ...groupPayload });
    }

    // ── Addon groups + their addons ──
    for (const ag of (body.addon_groups || [])) {
      const groupPayload = {
        name: ag.name,
        is_required: !!ag.is_required,
        min_select: ag.min_select || 0,
        max_select: ag.max_select || 1,
        sort_order: ag.sort_order ?? 0,
      };
      let groupId = ag.id;
      let oldAddons = [];
      if (ag.id && !ag.id.startsWith('ag_')) {
        await apiClient.patch(`/menu/items/${itemId}/addon-groups/${groupId}`, groupPayload);
        oldAddons = existingAddonGroups.find((g) => g.id === groupId)?.addons || [];
      } else {
        const created = await apiClient.post(`/menu/items/${itemId}/addon-groups`, groupPayload);
        groupId = created?.id;
      }
      // Same name-match reconciliation as variation options, so global add-on rows
      // keep their ids: PATCH /menu/addons/<id> for kept add-ons, POST for new ones,
      // archive for the ones the admin removed.
      const keptAddonIds = new Set();
      await Promise.all((ag.addons || []).map((addon, i) => {
        const payload = {
          name: addon.name,
          price: Number(addon.price) || 0,
          group_id: groupId,
          is_available: addon.is_available !== false,
          sort_order: addon.sort_order ?? i,
        };
        const match = oldAddons.find((a) => a.name === addon.name && !keptAddonIds.has(a.id));
        if (match) { keptAddonIds.add(match.id); return apiClient.patch(`/menu/addons/${match.id}`, payload).catch(() => {}); }
        return apiClient.post('/menu/addons', payload).catch(() => {});
      }));
      await Promise.all(oldAddons
        .filter((a) => !keptAddonIds.has(a.id))
        .map((a) => apiClient.post(`/menu/addons/${a.id}/archive`).catch(() => {})));
      results.addon_groups.push({ id: groupId, ...groupPayload });
    }

    return { message: 'Modifiers saved', item_id: itemId, ...results };
  },

  // --- Events (verified: /events/admin, /events/:id, /events/:id/qr) ---
  async getEvents() { return unwrap(await apiClient.get('/events/admin'), 'events'); },
  async createEvent(body) { return apiClient.post('/events', body); },
  async updateEvent(id, body) { return apiClient.patch(`/events/${id}`, body); },
  async toggleEventPublish(id) {
    const eventsList = unwrap(await apiClient.get('/events/admin'), 'events');
    const ev = eventsList.find(e => e.id === id);
    if (!ev) throw new ApiError(404, 'Event not found');
    return apiClient.patch(`/events/${id}`, { is_published: !ev.is_published });
  },
  async deleteEvent(id) { return apiClient.delete(`/events/${id}`); },
  async getEventRegistrations(id) {
    // /events/:id/registrants returns 404 on the live backend — fall back to any
    // registrations embedded in the event detail, else an empty list.
    try {
      const ev = await apiClient.get(`/events/${id}`);
      return unwrap(ev.registrations || ev.attendees || ev.registrants, 'registrations', 'attendees');
    } catch { return []; }
  },
  async generateEventQR(id) { return apiClient.post(`/events/${id}/qr`); },
  // Event ticket tiers (GET /events/:id/tiers, POST /events/:id/tiers, PATCH /events/:id/tiers/:tier_id)
  async getEventTicketTiers(id) { return unwrap(await apiClient.get(`/events/${id}/tiers`), 'tiers'); },
  async createEventTicketTier(id, body) { return apiClient.post(`/events/${id}/tiers`, body); },
  // Tier update/delete are /events/tiers/<tier_id> (NO event_id in the path —
  // the tier row owns its event_id). eventId kept in the signature for call-site
  // compatibility but is intentionally unused in the URL.
  async updateEventTicketTier(eventId, tierId, body) { return apiClient.patch(`/events/tiers/${tierId}`, body); },
  async deleteEventTicketTier(eventId, tierId) { return apiClient.delete(`/events/tiers/${tierId}`); },
  // No /events/<id>/tickets sales route exists — the enriched tier comparison
  // view (GET /events/<id>/tiers/comparison) carries sold_count/available, so
  // normalise it into the { tiers[] } shape the Sales dashboard expects.
  async getEventTicketSales(id) {
    const tiers = unwrap(await apiClient.get(`/events/${id}/tiers/comparison`), 'tiers');
    return {
      tiers: (tiers || []).map((t) => ({
        id: t.id,
        name: t.name,
        price_wallet: t.price_naira ?? 0,
        price_naira: t.price_naira ?? 0,
        price_hp: t.price_hp ?? 0,
        quantity_sold: t.sold_count ?? 0,
        tickets_sold: t.sold_count ?? 0,
        quantity_available: t.capacity ?? t.available ?? 0,
        capacity: t.capacity ?? null,
      })),
    };
  },
  // Event registrant export / email-to-host (GET /admin/events/:id/tickets, /export, POST send-to-host)
  // Registrants live at /events/<id>/registrants (NOT /admin/events/<id>/tickets).
  // The JSON response is { event, registrants, total }; the export builds CSV
  // client-side from the same registrant rows, so both return the array.
  async getEventRegistrants(id, params = {}) { return unwrap(await apiClient.get(`/events/${id}/registrants`, params), 'registrants', 'attendees'); },
  async exportEventRegistrations(id) { return unwrap(await apiClient.get(`/events/${id}/registrants`), 'registrants', 'attendees'); },
  async emailEventRegistrationsToHost(id, body) { return apiClient.post(`/events/${id}/send-registrants-to-host`, body); },

  // --- Rewards (verified: /rewards, /rewards/admin/redemptions) ---
  async getRewards() { return unwrap(await apiClient.get('/rewards'), 'rewards'); },
  async createReward(body) { return apiClient.post('/rewards', body); },
  async updateReward(id, body) { return apiClient.patch(`/rewards/${id}`, body); },
  async deleteReward(id) { return apiClient.delete(`/rewards/${id}`); },
  async getRedemptions() { return unwrap(await apiClient.get('/rewards/admin/redemptions'), 'redemptions'); },
  // PATCH /rewards/admin/redemptions/:id { status, admin_notes?, actual_cost? }.
  // status ∈ {fulfilled, rejected} — the backend never sets 'approved', so the
  // old approveRedemption method was dead (the status check rejected it).
  // actual_cost is only meaningful when status='fulfilled'.
  async fulfillRedemption(id, body = {}) { return apiClient.patch(`/rewards/admin/redemptions/${id}`, { status: 'fulfilled', ...body }); },
  async rejectRedemption(id, body = {}) { return apiClient.patch(`/rewards/admin/redemptions/${id}`, { status: 'rejected', ...body }); },
  // Flash sales — POST /rewards/admin/flash-sales { reward_id, window_starts_at,
  // window_ends_at, quantity_limit, discount_pct }. hp_cost is server-computed
  // from the reward's economics + discount_pct (never sent by the client). The
  // reward editor's old flash_* columns were dead — this is the real flash path.
  async createFlashSale(body) { return apiClient.post('/rewards/admin/flash-sales', body); },
  // Dedicated reward image upload — POST /rewards/<id>/image { image_url }.
  async updateRewardImage(id, body) { return apiClient.post(`/rewards/${id}/image`, body); },

  // --- Marketplace (verified: /marketplace/admin/listings, /requests, /purchases, /codes/:id) ---
  async getMarketplaceListings(params = {}) { return unwrap(await apiClient.get('/marketplace/admin/listings', params), 'listings'); },
  // Admin listing detail — GET /marketplace/admin/listings/<id>. Enriched with
  // codes_total, codes_remaining and purchase_count (computed server-side).
  async getMarketplaceListing(id) { return apiClient.get(`/marketplace/admin/listings/${id}`); },
  async createListing(body) { return apiClient.post('/marketplace/admin/listings', body); },
  async updateListing(id, body) { return apiClient.patch(`/marketplace/admin/listings/${id}`, body); },
  async deleteListing(id) { return apiClient.delete(`/marketplace/admin/listings/${id}`); },
  // Dedicated image update — POST /marketplace/admin/listings/<id>/image { image_url }.
  // The create/update listing routes also accept image_url, but this is the
  // image-only endpoint for direct uploads.
  async updateListingImage(id, body) { return apiClient.post(`/marketplace/admin/listings/${id}/image`, body); },
  // Per-campus availability override — PATCH /marketplace/admin/listings/<id>/availability.
  // Body: { campus_id?, inventory_count, low_inventory_threshold, is_out_of_stock, price_override }.
  // campus_id resolves server-side from the admin's JWT/X-Campus-ID when omitted.
  async updateListingAvailability(id, body) { return apiClient.patch(`/marketplace/admin/listings/${id}/availability`, body); },
  async getListingRequests() { return unwrap(await apiClient.get('/marketplace/admin/requests'), 'requests'); },
  // Approve/reject a vendor request — PATCH /marketplace/admin/requests/<id> { status, admin_notes? }.
  async approveListingRequest(id, body = {}) { return apiClient.patch(`/marketplace/admin/requests/${id}`, { status: 'approved', ...body }); },
  async rejectListingRequest(id, body = {}) { return apiClient.patch(`/marketplace/admin/requests/${id}`, { status: 'rejected', ...body }); },
  async uploadListingCodes(listingId, body) { return apiClient.post(`/marketplace/admin/codes/${listingId}`, body); },
  async getMarketplacePurchases(params = {}) { return unwrap(await apiClient.get('/marketplace/admin/purchases', params), 'purchases'); },
  // General purchase status update — PATCH /marketplace/admin/purchases/<id> { status, admin_note? }.
  // status ∈ {pending, completed, refunded, cancelled}. refunded/cancelled trigger
  // a real wallet+HP refund server-side; completed fulfils the code delivery.
  async updateMarketplacePurchase(id, body) { return apiClient.patch(`/marketplace/admin/purchases/${id}`, body); },
  async fulfillMarketplacePurchase(id) { return apiClient.patch(`/marketplace/admin/purchases/${id}`, { status: 'completed' }); },
  // Code-problem reports — GET /marketplace/admin/reports?status=, PATCH /marketplace/admin/reports/<id>.
  // Resolve action ∈ {replace, refund, reject}; returns { message, status }.
  async getMarketplaceReports(params = {}) { return unwrap(await apiClient.get('/marketplace/admin/reports', params), 'reports'); },
  async resolveMarketplaceReport(id, body) { return apiClient.patch(`/marketplace/admin/reports/${id}`, body); },

  // --- Notifications (verified: /notifications/blasts) ---
  // POST /notifications/blasts — body: { title, body, channels, target_segment?, send_at? }.
  // Backend renames target_segment→segment and send_at→scheduled_at internally.
  // Immediate send returns { blast, sent_to }; scheduled returns { blast, message }.
  async sendNotificationBlast(body) { return apiClient.post('/notifications/blasts', body); },
  async getNotificationBlasts(params = {}) { return unwrap(await apiClient.get('/notifications/blasts', params), 'blasts'); },
  // GET /notifications/blasts/<id> — single blast detail (admin only).
  async getNotificationBlast(id) { return apiClient.get(`/notifications/blasts/${id}`); },

  // --- Feature Flags (GET /admin/feature-flags[/campus_id|/:name], POST, PATCH upsert) ---
  async getFeatureFlags(params = {}) { return unwrap(await apiClient.get('/admin/feature-flags', params), 'flags', 'feature_flags'); },
  async getFeatureFlag(name) { return unwrap(await apiClient.get(`/admin/feature-flags/${name}`), 'flag', 'feature_flag'); },
  async toggleFeatureFlag(name, body) { return apiClient.patch(`/admin/feature-flags/${name}`, body); },
  async createFeatureFlag(body) { return apiClient.post('/admin/feature-flags', body); },

  // --- Leaderboard Prize Fulfilment (admin_flags_bp: GET /admin/leaderboard-prizes?status=, PATCH /:id {status, notes}) ---
  // Backend returns a bare array enriched with full_name + phone; the PATCH
  // returns { message, record } — surface res.message verbatim.
  async getLeaderboardRewards(params = {}) { return unwrap(await apiClient.get('/admin/leaderboard-prizes', params), 'rewards', 'prizes', 'leaderboard_prizes'); },
  async fulfillLeaderboardReward(id, body: Record<string, unknown> = { status: 'fulfilled' }) { return apiClient.patch(`/admin/leaderboard-prizes/${id}`, body); },
  // --- Hall of Fame Fulfillment (GET /admin/hall-of-fame-rewards?status=, PATCH /:id {status, notes}) ---
  // Status flow: pending → fulfilled (backend enum: pending, fulfilled, cancelled).
  async getHallOfFameRewards(params = {}) { return unwrap(await apiClient.get('/admin/hall-of-fame-rewards', params), 'inductees', 'rewards', 'hall_of_fame_rewards'); },
  async updateHallOfFameReward(id, body) { return apiClient.patch(`/admin/hall-of-fame-rewards/${id}`, body); },

  // --- Reviews Admin (GET /admin/reviews) ---
  // F5 GAP (reported): "Promote to testimonial" called POST /admin/reviews/<id>/
  // promote — admin.py serves GET /admin/reviews only, in any method. The button is
  // removed instead of 404-ing on click. Homepage testimonials come from storefront
  // sections, so promotion needs a backend route that writes one.
  async getReviews(params = {}) { return unwrap(await apiClient.get('/admin/reviews', params), 'reviews'); },

  // --- Catering Requests (GET/POST /events/catering-requests, PATCH /:id) ---
  async getCateringRequests(params = {}) { return unwrap(await apiClient.get('/events/catering-requests', params), 'requests', 'catering_requests'); },
  async updateCateringRequest(id, body) { return apiClient.patch(`/events/catering-requests/${id}`, body); },
  // Event registrant export / email-to-host
  async getEventRegistrantList(id, params = {}) { return unwrap(await apiClient.get(`/events/${id}/registrants`, params), 'registrants', 'attendees'); },
  async sendRegistrantsToHost(id, body) { return apiClient.post(`/events/${id}/send-registrants-to-host`, body); },
  // POST /events/<id>/image { image_url } — dedicated image update. The create/
  // update event routes do NOT accept image_url, so uploads must go through here
  // or they are silently dropped.
  async updateEventImage(id, body) { return apiClient.post(`/events/${id}/image`, body); },

  // No dedicated server-side search endpoint — aggregate across the four list
  // endpoints with the query term (spec: users, orders, menu items, promo codes).
  async globalSearch(q) {
    const [u, o, m, p] = await Promise.allSettled([
      apiClient.get('/admin/users', { q }),
      apiClient.get('/admin/orders', { q }),
      apiClient.get('/menu/items', { q }),
      apiClient.get('/admin/promo-codes', { q }),
    ]);
    return {
      users: u.status === 'fulfilled' ? unwrap(u.value, 'users') : [],
      orders: o.status === 'fulfilled' ? unwrap(o.value, 'orders') : [],
      menu: m.status === 'fulfilled' ? unwrap(m.value, 'items') : [],
      promos: p.status === 'fulfilled' ? unwrap(p.value, 'promo_codes', 'codes') : [],
    };
  },

  // --- Storefront Sections (GET/POST/PATCH/DELETE /storefront/sections) ---
  // Full storefront lifecycle: hero, banner, promo, testimonial, share_template.
  // The CMS list is the admin's own editing surface, so it asks for the
  // inactive rows too (the public storefront route still hides them). Without
  // this, switching a section off removed it from the admin list for good.
  async getStorefrontSections(params = {}) { return unwrap(await apiClient.get('/storefront/sections', { include_inactive: '1', ...params }), 'sections'); },
  async createStorefrontSection(body) { return apiClient.post('/storefront/sections', body); },
  async updateStorefrontSection(id, body) { return apiClient.patch(`/storefront/sections/${id}`, body); },
  async deleteStorefrontSection(id) { return apiClient.delete(`/storefront/sections/${id}`); },

  // --- Departments & Academic Levels (verified: /admin/departments, /admin/academic-levels) ---
  // isActive maps to the backend's ?is_active= filter (undefined = active rows only).
  async getDepartments(isActive = undefined) {
    return unwrap(await apiClient.get('/admin/departments', isActive === undefined ? {} : { is_active: isActive }), 'departments');
  },
  async createDepartment(body) { return apiClient.post('/admin/departments', body); },
  async updateDepartment(id, body) { return apiClient.patch(`/admin/departments/${id}`, body); },
  async deleteDepartment(id) { return apiClient.delete(`/admin/departments/${id}`); },
  // DELETE deactivates (soft delete); POST /restore reactivates the same row.
  async restoreDepartment(id) { return apiClient.post(`/admin/departments/${id}/restore`); },
  // GET /departments/faculties → { faculties: [...] } — server-side, campus-aware
  // distinct list for the department form's suggestions.
  async getFaculties(params = {}) { return unwrap(await apiClient.get('/departments/faculties', params), 'faculties'); },
  async getAcademicLevels() { return unwrap(await apiClient.get('/admin/academic-levels'), 'levels', 'academic_levels'); },
  async createAcademicLevel(body) { return apiClient.post('/admin/academic-levels', body); },
  async updateAcademicLevel(id, body) { return apiClient.patch(`/admin/academic-levels/${id}`, body); },
  // DELETE soft-deletes (deactivate); POST /restore reactivates. Both return a
  // backend-owned { message } we surface verbatim.
  async deleteAcademicLevel(id) { return apiClient.delete(`/admin/academic-levels/${id}`); },
  async restoreAcademicLevel(id) { return apiClient.post(`/admin/academic-levels/${id}/restore`); },

  // --- Storefront (verified: /storefront/banners, /early-supporters, /newsletter) ---
  // include_inactive — the public list route only returns is_active rows, so an
  // admin could never see (or fix) a banner they had switched off. The admin
  // panel always asks for everything and shows the active state as a toggle.
  async getBanners(params = {}) { return unwrap(await apiClient.get('/storefront/banners', { include_inactive: '1', ...params }), 'banners'); },
  async updateBanner(id, body) { return apiClient.patch(`/storefront/banners/${id}`, body); },
  async createBanner(body) { return apiClient.post('/storefront/banners', body); },
  async getEarlySupporters() { return unwrap(await apiClient.get('/storefront/early-supporters'), 'early_supporters', 'sections'); },
  async addEarlySupporter(body) { return apiClient.post('/storefront/early-supporters', body); },
  async removeEarlySupporter(id) { return apiClient.delete(`/storefront/early-supporters/${id}`); },
  async getNewsletterSubscribers() { return unwrap(await apiClient.get('/storefront/newsletter'), 'subscribers', 'newsletter'); },
  async unsubscribeNewsletter(body) { return apiClient.post('/storefront/newsletter/unsubscribe', body); },

  // --- Operating Hours (storefront.py: GET public, PATCH admin, POST override admin) ---
  // GET /storefront/operating-hours → { schedule, today_override, is_open }.
  // PATCH /storefront/operating-hours { day, open_time, close_time, is_closed }.
  // POST /storefront/operating-hours/override { override_date, is_closed, open_time, close_time, reason }.
  async getOperatingHours() { return apiClient.get('/storefront/operating-hours'); },
  async updateOperatingHours(body) { return apiClient.patch('/storefront/operating-hours', body); },
  async setOperatingHoursOverride(body) { return apiClient.post('/storefront/operating-hours/override', body); },

  // --- Early Supporters edit (PATCH + photo) — previously only add/remove were wired. ---
  async updateEarlySupporter(id, body) { return apiClient.patch(`/storefront/early-supporters/${id}`, body); },
  async updateEarlySupporterPhoto(id, body) { return apiClient.post(`/storefront/early-supporters/${id}/photo`, body); },

  // --- Dedicated image-upload endpoints (storefront.py). Section/banner image
  // management also works via the PATCH body, but these endpoints exist for
  // direct image-only updates. ---
  async updateSectionImage(id, body) { return apiClient.post(`/storefront/sections/${id}/image`, body); },
  async updateBannerImage(id, body) { return apiClient.post(`/storefront/banners/${id}/image`, body); },
  async deleteBanner(id) { return apiClient.delete(`/storefront/banners/${id}`); },

  // --- Admin wallet transactions (wallet.py GET /wallet/admin/transactions) ---
  async getWalletTransactions(params = {}) { return unwrap(await apiClient.get('/wallet/admin/transactions', params), 'transactions'); },

  // --- Onboarding / Gifts (GET /admin/gifts/first-order-gifts, PATCH /:id; settings via /admin/gifts/settings/:key) ---
  // Phase 3 — paths corrected: the backend routes are /admin/first-order-gifts and /admin/first-order-gifts/:id (admin_gifts.py:21,52), not /admin/gifts/...
  async getFirstOrderGifts(params = {}) { return unwrap(await apiClient.get('/admin/first-order-gifts', params), 'gifts', 'first_order_gifts'); },
  async updateFirstOrderGiftStatus(id, body) { return apiClient.patch(`/admin/first-order-gifts/${id}`, body); },
  // Graduation claims admin — NOT on live backend (only user-side POST /graduation/claim exists)
  getGraduationClaims: naList,
  approveGraduationClaim: naWrite('approveGraduationClaim'),
  rejectGraduationClaim: naWrite('rejectGraduationClaim'),

  // --- Challenges / Milestones (GET/POST /challenges/admin, PATCH/DELETE /:id, POST /:id/grant) ---
  // Challenges = milestones with time_window weekly/monthly; badges = window null.
  // Backend routes live under /challenges/admin (challenges_bp), NOT /admin/milestones.
  async getChallengesAdmin(params = {}) { return unwrap(await apiClient.get('/challenges/admin', params), 'milestones', 'challenges'); },
  async createChallenge(body) { return apiClient.post('/challenges/admin', body); },
  async updateChallenge(id, body) { return apiClient.patch(`/challenges/admin/${id}`, body); },
  async deleteChallenge(id) { return apiClient.delete(`/challenges/admin/${id}`); },
  async grantChallenge(id, body) { return apiClient.post(`/challenges/admin/${id}/grant`, body); },

  // --- Analytics (verified: /analytics/sales, /hp, /referrals, /export) ---
  async getSalesTrend(params = {}) { return apiClient.get('/analytics/sales', params); },
  async getAnalyticsHp() {
    const r = await apiClient.get('/analytics/hp');
    if (!r || typeof r !== 'object' || Array.isArray(r)) return { hp_earned_active: 0, hp_spent: 0, hp_expired: 0, hp_pending: 0, hp_in_circulation: 0, redemption_rate: 0, tier_distribution: {} };
    const sub = r.summary || r.totals || r.hp || r.analytics || r.data || {};
    const pick = (keys) => {
      for (const k of keys) {
        const v = r[k] ?? sub[k];
        if (v != null && v !== '') { const n = Number(v); if (!isNaN(n)) return n; }
      }
      return 0;
    };
    return {
      hp_earned_active: pick(['hp_earned_active', 'hp_earned', 'earned_active', 'total_earned', 'earned', 'hp_earned_total', 'total_hp_earned']),
      hp_spent: pick(['hp_spent', 'spent', 'total_spent', 'hp_redeemed', 'redeemed', 'total_hp_spent']),
      hp_expired: pick(['hp_expired', 'expired', 'total_expired']),
      hp_pending: pick(['hp_pending', 'pending', 'hp_reserved', 'reserved', 'pending_hp']),
      hp_in_circulation: pick(['hp_in_circulation', 'in_circulation', 'active_balance', 'circulation', 'active_hp', 'hp_balance', 'balance', 'current_balance']),
      redemption_rate: pick(['redemption_rate', 'redemption', 'rate']),
      tier_distribution: r.tier_distribution || sub.tier_distribution || r.tiers || sub.tiers || {},
    };
  },
  async getAnalyticsReferrals() { return apiClient.get('/analytics/referrals'); },
  async exportAnalytics(type, params = {}) {
    return apiClient.getRaw('/analytics/export', { type, ...params });
  },

  // --- HP Economics (admin_economics.py — /admin/economics/*) ---
  // Stage 16 admin reporting: programme cost vs target, per-tier effective %,
  // and redemption cost analytics. All three respect a date range.
  async getEconomicsOverview(params = {}) { return apiClient.get('/admin/economics/overview', params); },
  async getEconomicsTierBreakdown(params = {}) { return unwrap(await apiClient.get('/admin/economics/tier-breakdown', params), 'tiers', 'breakdown', 'tier_breakdown'); },
  async getEconomicsRedemptionAnalytics(params = {}) { return apiClient.get('/admin/economics/redemption-analytics', params); },

  // --- Delivery Zones (verified: /delivery/admin/hostels, /delivery/admin/gates) ---
  async getDeliveryHostels() { return unwrap(await apiClient.get('/delivery/admin/hostels'), 'hostels'); },
  async createDeliveryHostel(body) { return apiClient.post('/delivery/admin/hostels', body); },
  async updateDeliveryHostel(id, body) { return apiClient.patch(`/delivery/admin/hostels/${id}`, body); },
  async deleteDeliveryHostel(id) { return apiClient.delete(`/delivery/admin/hostels/${id}`); },
  async getDeliveryGates() { return unwrap(await apiClient.get('/delivery/admin/gates'), 'gates'); },
  async createDeliveryGate(body) { return apiClient.post('/delivery/admin/gates', body); },
  async updateDeliveryGate(id, body) { return apiClient.patch(`/delivery/admin/gates/${id}`, body); },
  async deleteDeliveryGate(id) { return apiClient.delete(`/delivery/admin/gates/${id}`); },
  async restoreDeliveryGate(id) { return apiClient.patch(`/delivery/admin/gates/${id}`, { is_active: true }); },

  // --- Free Side Credits Admin (free_sides.py /free-sides/admin/*) ---
  // The sides customers pick from live in the free_side_items TABLE: the public
  // GET /free-sides reads it directly (_get_free_side_options) — the old
  // system_settings.free_side_options blob is dead, so admins curate items here.
  async getFreeSideItemsAdmin(params = {}) { return unwrap(await apiClient.get('/free-sides/admin/items', params), 'items'); },
  async createFreeSideItem(body) { return apiClient.post('/free-sides/admin/items', body); },
  async updateFreeSideItem(id, body) { return apiClient.patch(`/free-sides/admin/items/${id}`, body); },
  async deleteFreeSideItem(id) { return apiClient.delete(`/free-sides/admin/items/${id}`); },
  // POST /free-sides/admin/credits { user_id, credits (1-20), validity_days?, reason? }
  async grantFreeSideCredits(body) { return apiClient.post('/free-sides/admin/credits', body); },
  // Validity stays a settings PATCH — the grant route and the monthly jobs read it.
  async updateFreeSideValidityDays(body) { return apiClient.patch('/admin/settings/free_side_credits_validity_days', body); },
  // F5 GAP (reported): nothing lists granted credits for admins — free_sides.py has
  // POST /admin/credits only, and GET /admin/free-credits never existed. The phantom
  // list was removed from AdminFreeCredits.tsx; a grant ledger needs a backend route.

  // --- Exclusive Spin Admin (DB-backed prize pool — GET/POST/PATCH/DELETE /admin/exclusive-spin-pool) ---
  // Mismatch 5.10: runtime odds control now lives in the exclusive_spin pool
  // CRUD, not deploy-time config. Prizes can be global (campus_id null) or
  // campus-scoped — the admin UI must distinguish the two.
  async getExclusiveSpinTemplate() { return unwrap(await apiClient.get('/admin/exclusive-spin-pool'), 'items', 'prizes', 'pool', 'template_items'); },
  async updateExclusiveSpinTemplateItem(id, body) { return apiClient.patch(`/admin/exclusive-spin-pool/${id}`, body); },
  async createExclusiveSpinTemplateItem(body) { return apiClient.post('/admin/exclusive-spin-pool', body); },
  async deleteExclusiveSpinTemplateItem(id) { return apiClient.delete(`/admin/exclusive-spin-pool/${id}`); },
  async updateExclusiveSpinExtraCost(body) { return apiClient.patch('/admin/settings/exclusive_spin_extra_cost', body); },
  async updateExclusiveSpinValidityDays(body) { return apiClient.patch('/admin/settings/exclusive_spin_validity_days', body); },
  // F5 GAP (reported): GET /admin/exclusive-spin/history has no backend route
  // (admin.py serves the prize pool, the grant and the fulfilment list). The phantom
  // "Spin History" table was removed from AdminExclusiveSpin.tsx instead of sitting
  // there empty; a spin ledger needs a backend route.
  // Grant spin credits to one user — POST /admin/exclusive-spin-grant
  // { user_id, spins (1-10), validity_days?, reason? }.
  async grantExclusiveSpinCredits(body) { return apiClient.post('/admin/exclusive-spin-grant', body); },
  // --- Exclusive Spin Prize Fulfilment (admin_flags_bp: GET /admin/exclusive-spin-prizes?status=, PATCH /:id {status, notes}) ---
  async getExclusiveSpinPrizes(params = {}) { return unwrap(await apiClient.get('/admin/exclusive-spin-prizes', params), 'prizes', 'exclusive_spin_prizes'); },
  async fulfillExclusiveSpinPrize(id, body = { status: 'fulfilled' }) { return apiClient.patch(`/admin/exclusive-spin-prizes/${id}`, body); },

  // --- Stock / Ingredient Tracking (GET/POST /admin/stock-items, POST /:id/purchase, /:id/usage, GET /:id/ledger) ---
  async getStockItems() { return unwrap(await apiClient.get('/admin/stock-items'), 'items', 'stock_items'); },
  async createStockItem(body) { return apiClient.post('/admin/stock-items', body); },
  async logStockPurchase(id, body) { return apiClient.post(`/admin/stock-items/${id}/purchase`, body); },
  async logStockUsage(id, body) { return apiClient.post(`/admin/stock-items/${id}/usage`, body); },
  async getStockItemLedger(id) { return unwrap(await apiClient.get(`/admin/stock-items/${id}/ledger`), 'entries', 'ledger', 'transactions'); },
  // Measurement units (GET /measurement-units → [{id, name}]) — powers the unit
  // dropdowns on the stock item form, which submits purchase_unit_id / usage_unit_id.
  async getMeasurementUnits() { return unwrap(await apiClient.get('/measurement-units'), 'measurement_units', 'units'); },
};

// ========== DEPARTMENTS & ACADEMIC LEVELS (student-facing) ==========
// Public student endpoints (departments.py / academic_levels.py) — NOT the
// /admin/* versions. Used by Profile to let students pick their department + level.
const departments = {
  async list() { return unwrap(await apiClient.get('/departments'), 'departments'); },
};
const academicLevels = {
  async list() { return unwrap(await apiClient.get('/academic-levels'), 'levels', 'academic_levels'); },
  // Single-level detail — GET /academic-levels/:level_id (public).
  async get(id) { return apiClient.get(`/academic-levels/${id}`); },
};

// ========== CAMPUSES (public, Domain 0) ==========
// Public campus list for the guest campus-selection gate. campuses RLS allows
// everyone to select; if the public endpoint is absent this resolves to [] and
// the gate never activates (single-campus / global fallback).
const campuses = {
  async list() { return unwrap(await apiClient.get('/campuses'), 'campuses'); },
};

// ========== DELIVERY ==========
const delivery = {
  async getHostels() { return unwrap(await apiClient.get('/delivery/hostels'), 'hostels'); },
  async getGates() { return unwrap(await apiClient.get('/delivery/gates'), 'gates'); },
  async calculateFee(body) { return apiClient.post('/delivery/calculate-fee', body); },
};

// ========== ORDER LOCKS ==========
// Backend (order_locks.py): POST creates a lock (reward_type 'discount'|'hp';
// discount_pct/reward_hp_amount come from system settings, never the client).
// GET /order-locks → { locks, count }; GET /order-locks/<id> → { lock }.
// PATCH /<id>/reschedule (once only); DELETE /<id> cancels.
const orderLocks = {
  async list(params = {}) { return apiClient.get('/order-locks', params); },
  async get(id) { return apiClient.get(`/order-locks/${id}`); },
  async create(body) { return apiClient.post('/order-locks', body); },
  async cancel(id) { return apiClient.delete(`/order-locks/${id}`); },
  async reschedule(id, body) { return apiClient.patch(`/order-locks/${id}/reschedule`, body); },
};

// ========== SQUADS ==========
// Managed squads — organizer-built rosters, campus-scoped. Base path /api/squads.
const squads = {
  // Both squads I created and squads I'm a roster member of.
  async list() { return unwrap(await apiClient.get('/squads'), 'squads'); },
  async create(body) { return apiClient.post('/squads', body); },
  async get(id) { return apiClient.get(`/squads/${id}`); },
  async getOrders(id) { return unwrap(await apiClient.get(`/squads/${id}/orders`), 'orders'); },
  async addMember(id, body) { return apiClient.post(`/squads/${id}/members`, body); },
  async removeMember(id, memberId) { return apiClient.delete(`/squads/${id}/members/${memberId}`); },
};

// ========== SAVED ITEMS ==========
const saved = {
  async list() { return unwrap(await apiClient.get('/saved'), 'saved', 'items'); },
  async add(body) { return apiClient.post('/saved', body); },
  async remove(id) { return apiClient.delete(`/saved/${id}`); },
  // Update quantity/notes on a saved item — PATCH /api/saved/<item_id>.
  async update(id, body) { return apiClient.patch(`/saved/${id}`, body); },
  async moveToCart(id) { return apiClient.post(`/saved/${id}/move-to-cart`); },
  // Save a cart item for later in one call — POST /api/saved/from-cart/{cart_item_id}.
  async fromCart(cartItemId) { return apiClient.post(`/saved/from-cart/${cartItemId}`); },
};

// ========== CHALLENGES ==========
const challenges = {
  async list(params = {}) { return unwrap(await apiClient.get('/challenges', params), 'challenges'); },
  async badges() { return unwrap(await apiClient.get('/challenges/badges'), 'badges', 'challenges'); },
  // NOT unwrapped: GET /challenges/my returns {badges, challenges_available,
  // challenges_completed} (milestone_service.get_user_milestones) — there is no
  // `challenges` key, so unwrap() returned [] and both challenge lists rendered
  // empty. Callers read the envelope directly.
  async my(params = {}): Promise<MyChallengesEnvelope> { return apiClient.get('/challenges/my', params); },
  // F6: `get(id)` was deleted — it called GET /challenges/<id>, which no backend
  // route serves, and nothing in the app called it. Milestones come from my()
  // (per-user) or the admin list.
  // Backend route reads no body (challenges.py:135 POST /<milestone_id>/complete).
  async complete(id) { return apiClient.post(`/challenges/${id}/complete`); },
  // Register a Web Push subscription AND claim the push-subscribe milestone /
  // PWA-push bonus — POST /challenges/push-subscribed { subscription, device_label }.
  // /push/subscribe only stores the row, so the bonus went unclaimed until this was
  // wired. It 404s when the milestone is not configured, so callers keep the plain
  // registration and swallow this one's failure.
  async pushSubscribed(body) { return apiClient.post('/challenges/push-subscribed', body); },
  // POST /challenges/social-follow — no ID in path; the backend looks up the social_follow milestone internally.
  async socialFollow(body) { return apiClient.post('/challenges/social-follow', body); },
};

// ========== GRADUATION ==========
const graduation = {
  async claim(body) { return apiClient.post('/graduation/claim', body); },
};

// ========== STOREFRONT (public) ==========
// Public storefront sections — used by the share-with-image flow to fetch the
// admin-uploaded base template (section_type='share_template') and by the
// homepage for banners / early-supporter content.
const storefront = {
  async getSections(params = {}) { return unwrap(await apiClient.get('/storefront/sections', params), 'sections'); },
  // Public carousel banners (storefront.py) — each banner has an `images` array
  // rendered as a swipeable carousel on the homepage. Optional placement filter.
  async getBanners(params = {}) { return unwrap(await apiClient.get('/storefront/banners', params), 'banners'); },
  // Public early-supporters list (storefront.py list_early_supporters).
  async getEarlySupporters() { return unwrap(await apiClient.get('/storefront/early-supporters'), 'early_supporters', 'sections'); },
  // Public newsletter subscribe (storefront.py newsletter_subscribe).
  async subscribeNewsletter(body) { return apiClient.post('/storefront/newsletter', body); },
  // Public operating hours (storefront.py get_hours) → { schedule, today_override, is_open }.
  async getOperatingHours() { return apiClient.get('/storefront/operating-hours'); },
  // Public system config (storefront.py get_public_config) — WhatsApp number, platform name, etc.
  async getPublicConfig() { return apiClient.get('/storefront/config/public'); },
  // --- Newsletter campaigns (storefront.py newsletter_campaigns_*; admin only) ---
  // Plain text only (HTML-escaped server-side); the backend computes the audience
  // (campus admins always send to their own campus, super_admin picks campus/all).
  async getNewsletterCampaigns(params = {}) { return await apiClient.get('/storefront/newsletter/campaigns', params) || []; },
  async createNewsletterCampaign(body) { return apiClient.post('/storefront/newsletter/campaigns', body); },
  async getNewsletterCampaign(id) { return apiClient.get(`/storefront/newsletter/campaigns/${id}`); },
  // Sends to the calling admin's own address only; nothing is stored.
  async sendNewsletterTest(body) { return apiClient.post('/storefront/newsletter/campaigns/test', body); },
  async cancelNewsletterCampaign(id) { return apiClient.post(`/storefront/newsletter/campaigns/${id}/cancel`); },
};

// ========== PUBLIC CONFIG ==========
// Public, unauthenticated system settings (WhatsApp number, streak rewards,
// free-side options, etc.). Students cannot read /admin/settings, so this is
// the student-facing source of configurable values. Falls back gracefully.
//
// ========== HEALTH (public, Domain 17 — GET /health) ==========
// Unauthenticated API health check: API status + Supabase and Redis connectivity.
const health = {
  async check() { return apiClient.get('/health'); },
};

// Export unified API — same interface as mockApi
export const liveApi = {
  auth, addresses, menu, cart, orders, events, hp, rewards, marketplace,
  wallet, notifications, push, referrals, leaderboard, kitchen, riders, analytics, admin, delivery, orderLocks, squads,
  saved, challenges, graduation, departments, academicLevels, campuses, storefront, health, users,
  demoLogin() {
    // No-op for live API — use login() instead
    console.warn('demoLogin is not available with the live API. Use login() instead.');
  },
  getState() { return null; },
};

export { isAuthenticated, clearTokens };