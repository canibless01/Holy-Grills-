/**
 * Admin section registry — single source of truth for the sidebar groups,
 * the global search's section matcher, and any other surface that needs the
 * full list of admin pages.
 *
 * Each section carries a `keywords` array so the search bar can match by
 * intent ("create menu" → menu, "multiplier" → hp, "assign batch" → delivery)
 * rather than only by the visible label.
 */
import {
  BarChart3, TrendingUp, Coins, UtensilsCrossed, Layers, Flame, Gift, Zap, Target,
  Package, Calendar, CalendarDays, ShoppingBag, Tag, ShoppingCart, Star, Users, Truck, Lock,
  Bell, Trophy, School, Store, GraduationCap, ToggleRight, SlidersHorizontal, Server,
  Boxes, Webhook, Wallet,
} from 'lucide-react';

export const ADMIN_GROUPS = [
  { label: null, items: [
    { id: 'dashboard', label: 'Dashboard', icon: BarChart3, desc: 'Live overview', keywords: ['overview', 'home', 'stats', 'summary'] },
    { id: 'analytics', label: 'Analytics', icon: TrendingUp, desc: 'Trends & exports', keywords: ['analytics', 'trends', 'reports', 'charts', 'data', 'export', 'dashboard', 'revenue', 'retention', 'engagement', 'demographics', 'cohort'] },
    { id: 'economics', label: 'HP Economics', icon: Coins, desc: 'Programme cost', keywords: ['economics', 'cost', 'budget', 'programme', 'tier breakdown'] },
  ]},
  { label: 'Menu', items: [
    { id: 'menu', label: 'Menu Items', icon: UtensilsCrossed, desc: 'Food items', keywords: ['create menu', 'menu item', 'food', 'dish', 'price', 'availability', 'sold out', 'kitchen capacity'] },
    { id: 'addons', label: 'Addons & Variations', icon: Layers, desc: 'Modifiers', keywords: ['addon', 'variation', 'modifier', 'extra', 'group', 'option'] },
  ]},
  { label: 'HP & Rewards', items: [
    { id: 'hp', label: 'HP & Multipliers', icon: Flame, desc: 'Earning rates', keywords: ['multiplier', 'hp', 'points', 'earning', 'rate', 'holy points'] },
    { id: 'rewards', label: 'Rewards', icon: Gift, desc: 'Redemptions', keywords: ['reward', 'redeem', 'redemption', 'fulfill'] },
    { id: 'freecredits', label: 'Free Credits', icon: Gift, desc: 'Side credits', keywords: ['free credit', 'free side', 'side credit'] },
    { id: 'exclusivespin', label: 'Exclusive Spin', icon: Zap, desc: 'Leaderboard spin', keywords: ['spin', 'exclusive', 'wheel', 'prize pool', 'odds'] },
    { id: 'challenges', label: 'Challenges', icon: Target, desc: 'Milestones', keywords: ['challenge', 'milestone', 'badge', 'quest', 'grant'] },
  ]},
  { label: 'Commerce', items: [
    { id: 'orders', label: 'Orders', icon: Package, desc: 'All orders', keywords: ['order', 'fulfillment', 'status', 'refund', 'history'] },
    { id: 'wallet', label: 'Wallet', icon: Wallet, desc: 'Transactions', keywords: ['wallet', 'transaction', 'funding', 'top up', 'topup', 'credit', 'debit', 'balance', 'payment', 'ledger'] },
    { id: 'events', label: 'Events', icon: Calendar, desc: 'Campus events', keywords: ['event', 'ticket', 'tier', 'registrant', 'qr'] },
    { id: 'catering', label: 'Catering', icon: UtensilsCrossed, desc: 'Bulk requests', keywords: ['catering', 'bulk', 'request'] },
    { id: 'marketplace', label: 'Marketplace', icon: ShoppingBag, desc: 'Listings', keywords: ['marketplace', 'listing', 'sell', 'buy', 'code'] },
    { id: 'promos', label: 'Promo Codes', icon: Tag, desc: 'Discounts', keywords: ['promo', 'discount', 'code', 'coupon'] },
    { id: 'abandoned', label: 'Abandoned Carts', icon: ShoppingCart, desc: 'Recoveries', keywords: ['abandoned', 'cart', 'recovery', 'nudge'] },
    { id: 'reviews', label: 'Reviews', icon: Star, desc: 'Ratings & testimonials', keywords: ['review', 'rating', 'testimonial', 'feedback', 'promote'] },
  ]},
  { label: 'People & Ops', items: [
    { id: 'users', label: 'Users', icon: Users, desc: 'Students & staff', keywords: ['user', 'student', 'staff', 'account', 'role', 'deactivate'] },
    { id: 'delivery', label: 'Delivery', icon: Truck, desc: 'Zones & gates', keywords: ['delivery', 'zone', 'gate', 'hostel', 'batch', 'assign batch', 'delivery batch', 'fee'] },
    { id: 'orderlocks', label: 'Order Locks', icon: Lock, desc: 'Price locks', keywords: ['lock', 'price lock', 'order lock', 'reschedule'] },
    { id: 'store', label: 'Store / Stock', icon: Boxes, desc: 'Ingredients & inventory', keywords: ['store', 'stock', 'ingredient', 'inventory', 'purchase', 'usage', 'low stock', 'ledger'] },
    { id: 'notifications', label: 'Campaigns', icon: Bell, desc: 'Blasts & scheduling', keywords: ['notification', 'blast', 'campaign', 'push', 'message', 'schedule', 'segment'] },
    { id: 'leaderboard', label: 'Leaderboard', icon: Trophy, desc: 'Rankings & HoF', keywords: ['leaderboard', 'rank', 'hall of fame', 'hof', 'prize'] },
  ]},
  { label: 'Config', items: [
    { id: 'departments', label: 'Departments', icon: School, desc: 'Academic', keywords: ['department', 'faculty', 'academic', 'level'] },
    { id: 'storefront', label: 'Storefront', icon: Store, desc: 'Banners', keywords: ['storefront', 'banner', 'hero', 'promo section', 'early supporter', 'newsletter'] },
    { id: 'onboarding', label: 'Onboarding', icon: GraduationCap, desc: 'Gifts', keywords: ['onboarding', 'gift', 'first order', 'graduation'] },
    { id: 'flags', label: 'Feature Flags', icon: ToggleRight, desc: 'Toggles', keywords: ['flag', 'feature', 'toggle', 'feature flag'] },
    { id: 'settings', label: 'Settings', icon: SlidersHorizontal, desc: 'System', keywords: ['setting', 'config', 'system setting', 'operating hours'] },
    { id: 'academiccalendar', label: 'Academic Calendar', icon: CalendarDays, desc: 'Terms & holidays', keywords: ['academic', 'calendar', 'semester', 'exam', 'break', 'holiday', 'orientation', 'term'] },
    { id: 'webhooks', label: 'Webhook Events', icon: Webhook, desc: 'Delivery log', keywords: ['webhook', 'event', 'delivery', 'integration', 'log', 'retry'] },
    { id: 'system', label: 'System', icon: Server, desc: 'Cron & audit', keywords: ['system', 'cron', 'audit', 'log', 'server', 'job'] },
  ]},
];

// Flat list for search and other lookups.
export const ADMIN_SECTIONS = ADMIN_GROUPS.flatMap((g) => g.items);

// Fuzzy section match — returns sections whose label, desc, or keywords
// include every word in the query (case-insensitive). "create menu" matches
// "Menu Items" because both "create" and "menu" appear in its keywords/label.
export const matchSections = (query) => {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const terms = q.split(/\s+/).filter(Boolean);
  return ADMIN_SECTIONS.filter((s) => {
    const haystack = [s.label, s.desc, ...(s.keywords || [])].join(' ').toLowerCase();
    return terms.every((t) => haystack.includes(t));
  });
};