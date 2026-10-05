// src/lib/featureConfig.js
// Reads system settings from the backend so feature values (squad discount %,
// streak cycle days, referral HP, etc.) are configurable by admins via the
// System Settings panel instead of hardcoded in the frontend.
//
// Non-admin users may not have access to /admin/settings — in that case the
// fetch silently fails and getSetting() returns its defaultValue, so the app
// keeps working with sensible built-in defaults.

import { liveApi } from './liveApi';
import { localStore } from './storage';
import { mergeAdminSettings } from './settingsMerge';

export { mergeAdminSettings };

// Kept in sync with campusContext.tsx. Imported from there instead of
// importing getStoredCampusId(), because campusContext -> HolyGrillContext ->
// featureConfig is a cycle: the binding can be undefined at the moment this
// module evaluates. storage.ts imports nothing that leads back here.
const CAMPUS_STORAGE_KEY = 'hg_campus_id';

let settingsMap = {};
let flagsMap = {};
let flagsLoaded = false;

// ── Central Feature Flag Registry (Spec §1.5) ────────────────────────────
// Every UI feature flag lives here. When a flag is OFF the UI element is
// HIDDEN completely (not disabled). All flags are flipped ON for now; the
// backend (/admin/feature-flags) can override any flag at runtime, and when
// the flags list cannot be loaded we fall back to these built-in defaults so
// the app always works. TODO env/localStorage overrides can layer on top later.
export const FEATURE_FLAGS = {
  // ── Spec §1.5 UI surface flags ──
  show_leaderboard_prizes_ui: true,
  show_hall_of_fame_ui: true,
  show_badge_ui: true,
  show_spin_ui: true,
  show_marketplace_ui: true,
  show_hp_transfer_ui: true,
  onboarding_slides: true,
  hp_earn_animation: true,
  sound_fx: true,
  streak_counter_ui: true,
  tier_progress_bar: true,
  collectibles_shelf: true,
  leaderboard_rank_badge: true,
  closed_store_countdown: true,
  hp_proximity_nudge: true,
  push_permission_prompt: true,
  spin_confetti: true,
  // ── Backend feature flags (Config Reference). Defaults match the spec:
  //    ON  → leaderboard_prizes, free_side_credits, exclusive_spin,
  //          hall_of_fame, badge_system, spin_and_win, squad_orders,
  //          referral_milestones, hp_expiry_warnings, birthday_hp,
  //          scheduled_orders, daily_checkin, event_ticket_tiers.
  //    OFF → marketplace_general, hp_transfer, flash_redemptions,
  //          subscription_codes, abandoned_cart_nudge.
  //    These are fallbacks only — /admin/feature-flags overrides live.
  leaderboard_prizes: true,
  hall_of_fame: true,
  badge_system: true,
  spin_and_win: true,
  squad_orders: true,
  referral_milestones: true,
  hp_expiry_warnings: true,
  birthday_hp: true,
  scheduled_orders: true,
  daily_checkin: true,
  event_ticket_tiers: true,
  hp_multiplier: true,
  free_side_credits: true,
  exclusive_spin: true,
  marketplace_general: false,
  hp_transfer: false,
  flash_redemptions: false,
  subscription_codes: false,
  abandoned_cart_nudge: false,
};

// Load the feature-flag list from /admin/feature-flags. Students read this to
// decide which features to show (spin & win, HP transfer, marketplace, etc.).
// The endpoint is the same one admins toggle; non-admins may lack access — in
// that case the fetch silently fails and isFeatureEnabled falls back to its
// defaultValue so the app keeps working with sensible built-in defaults.
export async function loadFeatureFlags() {
  try {
    const flags = await liveApi.admin.getFeatureFlags();
    flagsMap = {};
    (flags || []).forEach((f) => {
      const name = f.feature_name || f.name;
      if (name) flagsMap[name] = f.is_active ?? f.enabled ?? false;
    });
    flagsLoaded = true;
    return flagsMap;
  } catch (e) {
    flagsLoaded = false;
    return {};
  }
}

export function isFlagLoaded() { return flagsLoaded; }

export async function loadSystemSettings() {
  // Students cannot read /admin/settings, so prefer the public config first
  // (WhatsApp number, streak rewards, free-side options, etc.). The real route
  // is GET /api/storefront/config/public, which returns a flat key→value map;
  // the old GET /settings call 404'd, so students only ever saw the built-in
  // defaults (docs/WIRING_AUDIT.md §3.2). Admins fall through to
  // /admin/settings for the full privileged set. Either failing is non-fatal —
  // getSetting() returns its built-in default.
  settingsMap = {};
  try {
    const publicConfig = await liveApi.storefront.getPublicConfig();
    Object.entries(publicConfig || {}).forEach(([key, value]) => {
      if (value !== null && value !== undefined) settingsMap[key] = value;
    });
  } catch (e) { /* public endpoint unavailable — try admin below */ }
  try {
    const adminSettings = await liveApi.admin.getSystemSettings();
    mergeAdminSettings(settingsMap, adminSettings, localStore.getItem(CAMPUS_STORAGE_KEY) || null);
  } catch (e) { /* admin endpoint not accessible — keep public/defaults */ }
  return settingsMap;
}

export function getSetting(key, defaultValue = null) {
  const val = settingsMap[key];
  if (val === undefined || val === null) return defaultValue;
  // Coerce numeric strings back to numbers.
  if (typeof val === 'string' && val !== '' && !isNaN(Number(val))) return Number(val);
  return val;
}

/**
 * Boolean read for on/off settings.
 *
 * `getSetting('whatsapp_support_enabled', true)` looks safe but is not: a value
 * stored as the *string* "false" (which is what the admin screen writes for an
 * unknown key) is truthy in JavaScript, so the switch could never be turned
 * off from the database. Every toggle-shaped setting must come through here.
 */
export function getBoolSetting(key, defaultValue = false) {
  const val = settingsMap[key];
  if (val === undefined || val === null) return defaultValue;
  if (typeof val === 'boolean') return val;
  if (typeof val === 'number') return val !== 0;
  if (typeof val === 'string') {
    const v = val.trim().toLowerCase();
    if (v === 'true' || v === '1' || v === 'yes' || v === 'on') return true;
    if (v === 'false' || v === '0' || v === 'no' || v === 'off' || v === '') return false;
  }
  return defaultValue;
}

/**
 * The same read as getSetting() WITHOUT the numeric coercion, for values that
 * are text even when they happen to be all digits.
 *
 * A WhatsApp number is the obvious case: stored as "2348012345678" it came
 * back from getSetting() as the number 2348012345678 (harmless), but as
 * "+234 801 234 5678" it came back as NaN — and `https://wa.me/NaN` is exactly
 * the "the button opens some other number, it never reads the table" report.
 * Anything shown as text, dropped into a URL or echoed back to the user must
 * come through here.
 */
export function getStringSetting(key, defaultValue = '') {
  const val = settingsMap[key];
  if (val === undefined || val === null) return defaultValue;
  if (typeof val === 'string') return val;
  if (typeof val === 'number' || typeof val === 'boolean') return String(val);
  return defaultValue;
}

// Feature flags — read from /admin/feature-flags (loadFeatureFlags) so toggling
// a flag in the admin panel immediately hides/shows the feature for students.
// Keys include: leaderboard_prizes, hall_of_fame, exclusive_spin,
// free_side_credits, badge_system, spin_and_win, marketplace_general,
// hp_transfer, flash_redemptions, daily_checkin, event_ticket_tiers.
// If the flags list loaded successfully we honour its value (including false).
// If it could not be loaded (non-admin / endpoint unavailable) we fall back to
// the caller's defaultValue so the app keeps working with built-in defaults.
export function isFeatureEnabled(key, defaultValue) {
  if (flagsLoaded && key in flagsMap) return flagsMap[key];
  // Legacy fallback: some flags are still stored as system settings.
  const setting = getSetting(key, undefined);
  if (typeof setting === 'boolean') return setting;
  if (typeof setting === 'string') return setting === 'true' || setting === '1';
  if (defaultValue !== undefined) return defaultValue;
  // Fall back to the central registry — default ON unless explicitly false.
  return FEATURE_FLAGS[key] !== false;
}

// ── Spec §1.5 UI flag accessors ──────────────────────────────────────────
// Thin named wrappers so call sites read clearly and every spec flag has an
// explicit, grep-able home. Each defaults to its registry value (all true now).
export const showLeaderboardPrizesUI = () => isFeatureEnabled('show_leaderboard_prizes_ui', true);
export const showHallOfFameUI = () => isFeatureEnabled('show_hall_of_fame_ui', true);
export const showBadgeUI = () => isFeatureEnabled('show_badge_ui', true);
export const showSpinUI = () => isFeatureEnabled('show_spin_ui', true);
export const showMarketplaceUI = () => isFeatureEnabled('show_marketplace_ui', true);
export const showHpTransferUI = () => isFeatureEnabled('show_hp_transfer_ui', true);
export const onboardingSlides = () => isFeatureEnabled('onboarding_slides', true);
export const hpEarnAnimation = () => isFeatureEnabled('hp_earn_animation', true);
export const soundFx = () => isFeatureEnabled('sound_fx', true);
export const streakCounterUI = () => isFeatureEnabled('streak_counter_ui', true);
export const tierProgressBar = () => isFeatureEnabled('tier_progress_bar', true);
export const collectiblesShelf = () => isFeatureEnabled('collectibles_shelf', true);
export const leaderboardRankBadge = () => isFeatureEnabled('leaderboard_rank_badge', true);
export const closedStoreCountdown = () => isFeatureEnabled('closed_store_countdown', true);
export const hpProximityNudge = () => isFeatureEnabled('hp_proximity_nudge', true);
export const pushPermissionPrompt = () => isFeatureEnabled('push_permission_prompt', true);
export const spinConfetti = () => isFeatureEnabled('spin_confetti', true);

// Free-side options shown in the checkout dropdown. Read from the
// free_side_options system setting; falls back to the spec default list.
export function getFreeSideOptions() {
  const opts = getSetting('free_side_options', null);
  if (Array.isArray(opts) && opts.length) return opts;
  return ['Fries', 'Coleslaw', 'Plantain', 'Gizzard'];
}

// Platform name — used for branding across the app.
export function getPlatformName() {
  return getSetting('platform_name', 'Holy Grills');
}

// Launch window end date — first-order gift promo deadline.
export function getLaunchWindowEndDate() {
  return getSetting('launch_window_end_date', null);
}

// First-order gift item name — shown on order confirmation.
export function getFirstOrderGiftItemName() {
  return getSetting('first_order_gift_item_name', 'Hot Dog');
}

// HP multiplier feature flag — controls whether menu item HP multipliers are shown.
export function isHpMultiplierEnabled() {
  return isFeatureEnabled('hp_multiplier', true);
}

// Login streak rewards — tiered per week via the login_streak_rewards system
// setting (JSON, e.g. {"1":25,"2":40,"3":60,"4+":80}). Returns the HP reward
// for the week the user is currently building toward.
export function getStreakRewardHp(streakDays) {
  const raw = getSetting('login_streak_rewards', null);
  let map = raw;
  if (typeof raw === 'string') { try { map = JSON.parse(raw); } catch { map = null; } }
  if (!map || typeof map !== 'object') map = { '1': 25, '2': 40, '3': 60, '4+': 80 };
  const week = Math.floor((streakDays || 0) / 7) + 1;
  return Number(map[String(week)] ?? map['4+'] ?? 25);
}