// src/lib/appConfig.js
// ──────────────────────────────────────────────────────────────────────────
// SINGLE SOURCE OF TRUTH for every configurable value in Holy Grills.
//
// Every value below is either:
//   • a DB-editable setting (system_settings / kitchen_settings / feature_flags)
//     — read live via getSetting() / isFeatureEnabled() so an admin change in
//       the Admin UI takes effect immediately, with NO redeploy; OR
//   • an env-variable-backed setting — the backend exposes these through the
//     same /settings + /admin/settings + /admin/feature-flags endpoints, so the
//     frontend reads the resolved value rather than hardcoding the default.
//
// NOTHING in the app should hardcode any of these numbers. Always import the
// relevant accessor from here. When the backend changes a limit (e.g. squad
// max items 3 → 4), the frontend picks it up on the next settings load — it
// never keeps using the stale value.
//
// The defaults below mirror the env defaults in the Config Reference. They are
// only used when the backend hasn't returned a value yet (first paint / endpoint
// unavailable), so the app always works.
// ──────────────────────────────────────────────────────────────────────────

import { getSetting, isFeatureEnabled } from './featureConfig';

// ── Helpers ──────────────────────────────────────────────────────────────────
const num = (key, fallback) => {
  const v = getSetting(key, fallback);
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
};
const bool = (key, fallback) => {
  const v = getSetting(key, fallback);
  if (typeof v === 'boolean') return v;
  if (typeof v === 'string') return v === 'true' || v === '1';
  return fallback;
};
const str = (key, fallback) => {
  const v = getSetting(key, fallback);
  return v == null ? fallback : String(v);
};
const json = (key, fallback) => {
  const v = getSetting(key, null);
  if (Array.isArray(v)) return v;
  if (v && typeof v === 'object') return v;
  if (typeof v === 'string') { try { return JSON.parse(v); } catch { /* keep fallback */ } }
  return fallback;
};

// ── SQUAD ORDERS ──────────────────────────────────────────────────────────────
export const squadOrderMinItems = () => num('squad_order_min_items', 3);
export const squadOrderMaxItems = () => num('squad_order_max_items', 20);
export const squadOrderDiscountEnabled = () => bool('squad_order_discount_enabled', false);
export const squadOrderDiscountPct = () => num('squad_order_discount_pct', 10);
export const squadDeliveryDiscountEnabled = () => bool('squad_delivery_discount_enabled', true);
export const squadDeliveryDiscountPct = () => num('squad_delivery_discount_pct', 100);
export const squadOrdersEnabled = () => isFeatureEnabled('squad_orders', true);

// ── HP EARNING / UNLOCKING ───────────────────────────────────────────────────
export const hpPerNairaFood = () => num('hp_per_naira_food', 0.1);
export const hpUnlockRatePct = () => num('hp_unlock_rate_pct', 0.30);
export const signupBonusHp = () => num('signup_bonus_hp', 0);
export const signupBonusEnabled = () => bool('signup_bonus_enabled', false);
export const welcomeBonusHp = () => num('welcome_bonus_hp', 50);
export const referralHp = () => num('referral_hp', 75);
export const eventCheckinHp = () => num('event_checkin_hp', 40);
export const reviewHp = () => num('review_hp', 20);
export const sharePromptHp = () => num('share_prompt_hp', 25);
export const walletTopupMin = () => num('wallet_topup_min', 3000);
export const walletTopupHp = () => num('wallet_topup_hp', 50);
export const graduationHp = () => num('graduation_hp', 1000);
export const birthdayHp = () => num('birthday_hp', 150);
export const hpMultiplier = () => num('hp_multiplier', 1.0);
export const hpMultiplierExpiresAt = () => str('multiplier_expires_at', null);
export const monthlyPendingCap = () => num('monthly_pending_cap', 1000);
export const hpTransferMinOrders = () => num('hp_transfer_min_orders', 3);
export const hpTransferMinAmount = () => num('hp_transfer_min_amount', 10);
export const birthdayHpEnabled = () => isFeatureEnabled('birthday_hp', true);
export const hpExpiryWarningsEnabled = () => isFeatureEnabled('hp_expiry_warnings', true);
export const referralMilestonesEnabled = () => isFeatureEnabled('referral_milestones', true);

// ── ORDER LOCKS ──────────────────────────────────────────────────────────────
export const orderLockMaxDiscountPct = () => num('order_lock_max_discount_pct', 50);
export const orderLockDefaultDiscountPct = () => num('order_lock_default_discount_pct', 10);
export const orderLockMaxReschedules = () => num('order_lock_max_reschedules', 1);
export const scheduledOrdersEnabled = () => isFeatureEnabled('scheduled_orders', true);

// ── STREAKS ───────────────────────────────────────────────────────────────────
// Login streak rewards are tiered per week: { "1": 25, "2": 40, "3": 60, "4+": 80 }
export const loginStreakRewards = () => json('login_streak_rewards', { '1': 25, '2': 40, '3': 60, '4+': 80 });
export const streakCycleDays = () => num('streak_cycle_days', 7);
export const dailyCheckinHp = () => num('daily_checkin_hp', 5);
export const dailyCheckinEnabled = () => isFeatureEnabled('daily_checkin', true);

// ── HP TRANSFER ───────────────────────────────────────────────────────────────
export const hpTransferEnabled = () => isFeatureEnabled('hp_transfer', false);

// ── REWARDS & MARKETPLACE ────────────────────────────────────────────────────
export const marketplacePurchaseHp = () => num('marketplace_purchase_hp', 50);
export const lowCodeInventoryThreshold = () => num('low_code_inventory_threshold', 5);
export const flashDiscountPct = () => num('flash_discount_pct', 0.50);
export const flashMaxQty = () => num('flash_max_qty', 5);
export const flashRedemptionsEnabled = () => isFeatureEnabled('flash_redemptions', false);
export const hpBundlePricePerHp = () => num('hp_bundle_price_per_hp', 5.0);
export const hpBundleMinPurchase = () => num('hp_bundle_min_purchase', 100);
export const hpBundles = () => json('hp_bundles', []);
export const freeSideOptions = () => json('free_side_options', ['Fries', 'Coleslaw', 'Plantain', 'Gizzard']);
export const freeSideCreditsValidityDays = () => num('free_side_credits_validity_days', 60);
export const freeSideCreditsEnabled = () => isFeatureEnabled('free_side_credits', true);
export const exclusiveSpinValidityDays = () => num('exclusive_spin_validity_days', 30);
export const exclusiveSpinEnabled = () => isFeatureEnabled('exclusive_spin', true);
export const spinAndWinEnabled = () => isFeatureEnabled('spin_and_win', true);
export const marketplaceGeneralEnabled = () => isFeatureEnabled('marketplace_general', false);
export const leaderboardPrizesEnabled = () => isFeatureEnabled('leaderboard_prizes', true);
export const hallOfFameEnabled = () => isFeatureEnabled('hall_of_fame', true);
export const badgeSystemEnabled = () => isFeatureEnabled('badge_system', true);
export const eventTicketTiersEnabled = () => isFeatureEnabled('event_ticket_tiers', true);
export const subscriptionCodesEnabled = () => isFeatureEnabled('subscription_codes', false);
export const abandonedCartNudgeEnabled = () => isFeatureEnabled('abandoned_cart_nudge', false);

// ── ORDERING WINDOWS / CAPACITY (kitchen_settings) ───────────────────────────
export const orderingWindowOpenTime = () => str('ordering_window_open_time', '08:00');
export const orderingWindowCloseTime = () => str('ordering_window_close_time', '16:00');
export const dailyOrderCapacity = () => num('daily_order_capacity', 0); // 0 = no cap
export const windowCapacity = () => num('window_capacity', 0); // 0 = no cap

// ── NOTIFICATIONS ─────────────────────────────────────────────────────────────
export const notificationGapMinutes = () => num('notification_gap_minutes', 30);
export const notificationDailyCap = () => num('notification_daily_cap', 20);

// ── GRADUATION ────────────────────────────────────────────────────────────────
export const graduationMinLevel = () => num('graduation_min_level', 500);

// ── PAYMENT / WALLET ──────────────────────────────────────────────────────────
export const walletMinCardTopup = () => num('wallet_min_card_topup', 100);
export const walletMinWithdrawal = () => num('wallet_min_withdrawal', 1000);
export const walletRefPrefix = () => str('wallet_ref_prefix', 'HG-WALLET-');
export const paystackPreferredBank = () => str('paystack_preferred_bank', 'wema-bank');

// ── BRANDING ─────────────────────────────────────────────────────────────────
export const appName = () => str('app_name', 'Holy Grills');
export const hpCurrencyName = () => str('hp_currency_name', 'HP');

// ── AGGREGATE: squad config object for convenience in the cart ───────────────
export const getSquadConfig = () => ({
  enabled: squadOrdersEnabled(),
  discountEnabled: squadOrderDiscountEnabled(),
  discountPct: squadOrderDiscountPct(),
  deliveryDiscountEnabled: squadDeliveryDiscountEnabled(),
  deliveryDiscountPct: squadDeliveryDiscountPct(),
  minItems: squadOrderMinItems(),
  maxItems: squadOrderMaxItems(),
});

// ── ORDER STATUS TRANSITIONS ─────────────────────────────────────────────────
// The backend enforces strict transitions. These maps encode the ONE valid
// next status for each current status so every panel only offers the legal
// next step (and never a jump). Terminal statuses (cancelled / refunded) have
// no next step.
export const STUDENT_NEXT_STATUS = {
  received: 'preparing',
  preparing: 'ready',
  ready: 'assigned',
  assigned: 'out_for_delivery',
  out_for_delivery: 'delivered',
  delivered: null,
  cancelled: null,
  refunded: null,
  delivery_attempted: null,
  unclaimed: null,
  scheduled: null,
};

export const KITCHEN_NEXT_STATUS = {
  received: 'preparing',
  preparing: 'ready',
  ready: null, // kitchen hands off to rider dispatch
};

export const RIDER_NEXT_STATUS = {
  out_for_delivery: 'delivered',
  delivered: null,
  delivery_attempted: 'unclaimed',
  unclaimed: null,
};

export const TERMINAL_STATUSES = ['cancelled', 'refunded', 'delivered', 'unclaimed'];

// Helper: the single valid next status for an order, or null if terminal.
export const nextStatusFor = (role, currentStatus) => {
  const map = role === 'kitchen' ? KITCHEN_NEXT_STATUS : role === 'rider' ? RIDER_NEXT_STATUS : STUDENT_NEXT_STATUS;
  return map[currentStatus] ?? null;
};

// Whether a status is terminal (no further transitions possible).
export const isTerminalStatus = (status) => TERMINAL_STATUSES.includes(status);

// ── HP multiplier banner data ────────────────────────────────────────────────
export const getActiveHpMultiplier = () => {
  const mult = hpMultiplier();
  const expires = hpMultiplierExpiresAt();
  if (!mult || mult <= 1) return null;
  const expired = expires && new Date(expires).getTime() < Date.now();
  if (expired) return null;
  return { multiplier: mult, expiresAt: expires };
};

// ── React hook: live config values that react to settings reloads ────────────
import { useHolyGrill } from './HolyGrillContext';
export function useAppConfig() {
  // systemSettings is re-published by HolyGrillContext whenever settings reload,
  // so reading accessors during render picks up the latest DB values. Touching
  // systemSettings here makes this hook re-run when settings refresh.
  // eslint-disable-next-line no-unused-expressions
  useHolyGrill().systemSettings;
  return {
    squad: getSquadConfig(),
    wallet: {
      minCardTopup: walletMinCardTopup(),
      minWithdrawal: walletMinWithdrawal(),
      topupMin: walletTopupMin(),
      topupHp: walletTopupHp(),
      refPrefix: walletRefPrefix(),
      preferredBank: paystackPreferredBank(),
    },
    hp: {
      perNairaFood: hpPerNairaFood(),
      unlockRatePct: hpUnlockRatePct(),
      welcomeBonus: welcomeBonusHp(),
      referral: referralHp(),
      eventCheckin: eventCheckinHp(),
      review: reviewHp(),
      sharePrompt: sharePromptHp(),
      graduation: graduationHp(),
      birthday: birthdayHp(),
      transferMin: hpTransferMinAmount(),
      transferMinOrders: hpTransferMinOrders(),
      monthlyPendingCap: monthlyPendingCap(),
      multiplier: getActiveHpMultiplier(),
    },
    rewards: {
      marketplacePurchaseHp: marketplacePurchaseHp(),
      lowStockThreshold: lowCodeInventoryThreshold(),
      flashDiscountPct: flashDiscountPct(),
      flashMaxQty: flashMaxQty(),
      hpBundlePricePerHp: hpBundlePricePerHp(),
      hpBundleMinPurchase: hpBundleMinPurchase(),
      hpBundles: hpBundles(),
      freeSideOptions: freeSideOptions(),
      freeSideValidityDays: freeSideCreditsValidityDays(),
      exclusiveSpinValidityDays: exclusiveSpinValidityDays(),
      graduationMinLevel: graduationMinLevel(),
      graduationHp: graduationHp(),
    },
    streak: {
      cycleDays: streakCycleDays(),
      rewards: loginStreakRewards(),
      dailyCheckinHp: dailyCheckinHp(),
    },
    kitchen: {
      windowOpen: orderingWindowOpenTime(),
      windowClose: orderingWindowCloseTime(),
      dailyCapacity: dailyOrderCapacity(),
      windowCapacity: windowCapacity(),
    },
    notifications: {
      gapMinutes: notificationGapMinutes(),
      dailyCap: notificationDailyCap(),
    },
    orderLocks: {
      maxDiscountPct: orderLockMaxDiscountPct(),
      defaultDiscountPct: orderLockDefaultDiscountPct(),
      maxReschedules: orderLockMaxReschedules(),
    },
    flags: {
      squadOrders: squadOrdersEnabled(),
      hpTransfer: hpTransferEnabled(),
      flashRedemptions: flashRedemptionsEnabled(),
      marketplaceGeneral: marketplaceGeneralEnabled(),
      freeSideCredits: freeSideCreditsEnabled(),
      exclusiveSpin: exclusiveSpinEnabled(),
      spinAndWin: spinAndWinEnabled(),
      leaderboardPrizes: leaderboardPrizesEnabled(),
      hallOfFame: hallOfFameEnabled(),
      badgeSystem: badgeSystemEnabled(),
      birthdayHp: birthdayHpEnabled(),
      hpExpiryWarnings: hpExpiryWarningsEnabled(),
      referralMilestones: referralMilestonesEnabled(),
      scheduledOrders: scheduledOrdersEnabled(),
      dailyCheckin: dailyCheckinEnabled(),
      eventTicketTiers: eventTicketTiersEnabled(),
      subscriptionCodes: subscriptionCodesEnabled(),
      abandonedCartNudge: abandonedCartNudgeEnabled(),
    },
    branding: { appName: appName(), hpCurrencyName: hpCurrencyName() },
    nextStatusFor,
    isTerminalStatus,
  };
}