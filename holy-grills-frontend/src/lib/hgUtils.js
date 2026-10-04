// HolyGrill utility helpers
//
// Tier data is loaded from the backend (GET /hp/tiers) into a module-level
// cache on app start (see HolyGrillContext → loadTiers). The sync tier
// functions below read from that cache. Before the first load completes
// the cache is empty and the functions return a minimal "unloaded" tier
// (slug 'ember', min_points 0) so the UI renders sensibly without crashing.

let tierCache = [];

// Load tiers from the backend into the module cache. Called once on app
// init by HolyGrillContext. Safe to call again to refresh.
export async function loadTiers() {
  try {
    const { liveApi } = await import('./liveApi');
    const tiers = await liveApi.hp.getTiers();
    tierCache = Array.isArray(tiers) ? tiers : [];
  } catch { tierCache = []; }
}

// Imperatively set the tier cache (e.g. from a component that already
// fetched tiers for its own use).
export function setTiers(tiers) { tierCache = Array.isArray(tiers) ? tiers : []; }
export function getTiers() { return tierCache; }

// Minimal placeholder returned while the backend tiers haven't loaded yet.
// Not mock data — just a loading-safe default so the sync functions never
// return undefined. Real thresholds/names/multipliers come from the backend.
const UNLOADED_TIER = { id: null, name: '—', slug: 'ember', min_points: 0, earn_multiplier: 1, icon: '🔥', color: '#A8301A' };

export const formatNaira = (amount) => {
  return `₦${(amount || 0).toLocaleString('en-NG', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
};

export const formatHp = (amount) => {
  return `${amount || 0} HP`;
};

export const formatDate = (dateStr) => {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-NG', { day: 'numeric', month: 'short', year: 'numeric' });
};

export const formatDateTime = (dateStr) => {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-NG', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
};

export const formatTime = (dateStr) => {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  return d.toLocaleTimeString('en-NG', { hour: '2-digit', minute: '2-digit' });
};

export const timeAgo = (dateStr) => {
  if (!dateStr) return '—';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return formatDate(dateStr);
};

export const getTier = (hpEarned120Day) => {
  if (!tierCache.length) return UNLOADED_TIER;
  let current = tierCache[0];
  for (const tier of tierCache) {
    if (hpEarned120Day >= tier.min_points) current = tier;
  }
  return current;
};

export const getNextTier = (hpEarned120Day) => {
  for (const tier of tierCache) {
    if (hpEarned120Day < tier.min_points) return tier;
  }
  return null;
};

export const getTierProgress = (hpEarned120Day) => {
  const current = getTier(hpEarned120Day);
  const next = getNextTier(hpEarned120Day);
  if (!next) return { current, next: null, progress: 100, remaining: 0 };
  const range = next.min_points - current.min_points;
  const earned = hpEarned120Day - current.min_points;
  return { current, next, progress: Math.min(100, (earned / range) * 100), remaining: next.min_points - hpEarned120Day };
};

// Continuous progress across the ENTIRE tier ladder (first tier → last tier).
// Unlike getTierProgress (which resets to 0% at each tier boundary), this never
// empties out when a new tier unlocks — the fill keeps climbing toward the final
// tier, so the bar only ever grows. Used by the dashboard HP progress bar.
export const getTierOverallProgress = (hpEarned120Day) => {
  if (!tierCache.length) return { progress: 0, lastTier: UNLOADED_TIER };
  const firstMin = tierCache[0].min_points || 0;
  const lastTier = tierCache[tierCache.length - 1];
  const span = lastTier.min_points - firstMin;
  const progress = span > 0 ? Math.min(100, ((hpEarned120Day - firstMin) / span) * 100) : 100;
  return { progress, lastTier };
};

export const ORDER_STATUS_FLOW = ['received', 'preparing', 'ready', 'assigned', 'out_for_delivery', 'delivered'];

export const ORDER_STATUS_LABELS = {
  received: 'Order Received',
  preparing: 'Preparing',
  ready: 'Ready for Pickup',
  assigned: 'Rider Assigned',
  out_for_delivery: 'Out for Delivery',
  delivered: 'Delivered',
  cancelled: 'Cancelled',
  refunded: 'Refunded',
  delivery_attempted: 'Delivery Attempted',
  unclaimed: 'Unclaimed',
  scheduled: 'Scheduled',
};

export const ORDER_STATUS_COLORS = {
  received: 'bg-gradient-cta text-white',
  preparing: 'bg-gradient-cta text-white',
  ready: 'bg-gradient-cta text-white',
  assigned: 'bg-gradient-cta text-white',
  out_for_delivery: 'bg-gradient-cta text-white',
  delivered: 'bg-accent/80 text-white',
  cancelled: 'bg-primary/90 text-white',
  refunded: 'bg-primary/90 text-white',
  delivery_attempted: 'bg-gradient-cta text-white',
  unclaimed: 'bg-primary/90 text-white',
  scheduled: 'bg-gradient-cta text-white',
};

// Extract the ordering student's identity (name / phone / email) from an order
// object across every field shape the backend has been seen to return.
// Used by the Kitchen, Admin, Rider, and Student panels so they all surface
// "who placed this order" consistently — the order carries the info, the panels
// just have to read it out of the right field.
export const getOrderCustomer = (o) => {
  if (!o) return { name: '', phone: '', email: '', display: 'Walk-in' };
  const name =
    o.customer_name ||
    (o.customer && (o.customer.name || o.customer.full_name)) ||
    (o.delivery_contact && (o.delivery_contact.full_name || o.delivery_contact.name)) ||
    o.delivery_contact_name ||
    (o.user && (o.user.full_name || o.user.name)) ||
    o.guest_name ||
    o.user_name ||
    '';
  const phone =
    o.customer_phone ||
    (o.customer && o.customer.phone) ||
    (o.delivery_contact && o.delivery_contact.phone) ||
    o.delivery_contact_phone ||
    o.guest_phone ||
    (o.user && o.user.phone) ||
    '';
  const email =
    o.customer_email ||
    (o.customer && o.customer.email) ||
    (o.delivery_contact && o.delivery_contact.email) ||
    (o.user && o.user.email) ||
    o.user_email ||
    '';
  const display = name || (phone ? phone : 'Walk-in');
  return { name: name || '', phone: phone || '', email: email || '', display };
};

export const NOTIFICATION_ICONS = {
  order_status: '📦',
  order_confirmed: '✅',
  hp_earned: '🔥',
  streak_reminder: '📅',
  event_reminder: '🎟️',
  birthday: '🎂',
  promo: '⚡',
  delivery_update: '🛵',
};

export const HP_SOURCE_LABELS = {
  food_order: 'Food Order',
  event_checkin: 'Event Check-in',
  review: 'Review',
  social_share: 'Social Share',
  login_streak: 'Login Streak',
  spin_wheel: 'Spin Wheel',
  wallet_topup: 'Wallet Top-up',
  welcome_bonus: 'Welcome Bonus',
  signup_bonus: 'Sign-up Bonus',
  referral: 'Referral',
  birthday: 'Birthday Gift',
  order_discount: 'Order Discount',
  admin_grant: 'Admin Grant',
  challenge: 'Challenge',
  flash_redeem: 'Flash Redeem',
};

// ── TIER ACCENT SYSTEM ──
// Maps each tier to a cohesive accent palette used across the dashboard,
// header avatar ring, and greeting icon. Classes are literal strings so
// Tailwind's JIT scanner picks them up from this source file.
export const TIER_ACCENTS = {
  ember: {
    slug: 'ember',
    icon: '🔥',
    text: 'text-primary',
    bg: 'bg-primary',
    gradient: 'bg-gradient-cta',
    ring: 'ring-primary',
    light: 'bg-primary/10',
    lightBorder: 'border-primary/15',
  },
  flame: {
    slug: 'flame',
    icon: '🕯️',
    text: 'text-primary',
    bg: 'bg-primary',
    gradient: 'bg-gradient-to-br from-accent to-primary',
    ring: 'ring-primary',
    light: 'bg-accent/10',
    lightBorder: 'border-accent/30',
  },
  blaze: {
    slug: 'blaze',
    icon: '💥',
    text: 'text-accent-foreground',
    bg: 'bg-accent-foreground',
    gradient: 'bg-gradient-to-br from-accent/80 to-accent-foreground',
    ring: 'ring-accent-foreground',
    light: 'bg-accent/10',
    lightBorder: 'border-accent/50',
  },
  holy: {
    slug: 'holy',
    icon: '👑',
    text: 'text-accent-foreground',
    bg: 'bg-accent-foreground',
    gradient: 'tier-shimmer-holy',
    ring: 'ring-accent/80',
    light: 'bg-accent/10',
    lightBorder: 'border-accent/50',
    shimmer: true,
  },
};

export const getTierAccent = (hpEarned120Day) => {
  const tier = getTier(hpEarned120Day);
  return TIER_ACCENTS[tier.slug] || TIER_ACCENTS.ember;
};

// ── TIER PROGRESSION GRADIENT ──
// Each tier has a from→to gradient made from brand colours only. As the user
// earns HP and approaches the next tier, the gradient interpolates toward the
// next tier's gradient — so the login streak card visibly "heats up".
//   ember  : red → yellow   (the streak-counter / cta gradient)
//   flame  : yellow → brown
//   blaze  : brown → gold
//   holy   : gold (solid — top tier)
const TIER_GRADIENT_COLORS = {
  ember: { from: '#E70E0E', to: '#F2B84B' },
  flame: { from: '#F2B84B', to: '#6A1F00' },
  blaze: { from: '#6A1F00', to: '#F2B84B' },
  holy:  { from: '#F2B84B', to: '#F2B84B' },
};

function hexLerp(hex1, hex2, t) {
  const parse = (h) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
  const [r1, g1, b1] = parse(hex1);
  const [r2, g2, b2] = parse(hex2);
  const toHex = (n) => Math.round(n).toString(16).padStart(2, '0');
  return `#${toHex(r1 + (r2 - r1) * t)}${toHex(g1 + (g2 - g1) * t)}${toHex(b1 + (b2 - b1) * t)}`;
}

// Returns a CSS linear-gradient string that transitions from the current tier's
// gradient toward the next tier's gradient based on progress %.
//   0–49%  → current tier gradient (no blend)
//   50–74% → partial blend toward next
//   75–99% → next tier dominant
//   100%   → next tier gradient solid
export const getTierProgressGradient = (hpEarned120Day) => {
  const { current, next, progress } = getTierProgress(hpEarned120Day);
  const cur = TIER_GRADIENT_COLORS[current.slug] || TIER_GRADIENT_COLORS.ember;
  if (!next) return `linear-gradient(135deg, ${cur.from}, ${cur.to})`;
  const nxt = TIER_GRADIENT_COLORS[next.slug] || cur;
  let t;
  if (progress < 50) t = 0;
  else if (progress < 75) t = (progress - 50) / 25 * 0.5;
  else t = 0.5 + (progress - 75) / 25 * 0.5;
  const from = hexLerp(cur.from, nxt.from, t);
  const to = hexLerp(cur.to, nxt.to, t);
  return `linear-gradient(135deg, ${from}, ${to})`;
};