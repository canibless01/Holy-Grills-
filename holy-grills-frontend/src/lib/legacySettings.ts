// Reconciled against live setting keys + current Python/SQL/React consumers.
// Preserve stored values; do not silently connect obsolete keys to money rules.
const storedOnly = new Set([
  'ambassador_expected_weekly_shares', 'ambassador_meal_discount_default_max',
  'currency_code', 'currency_symbol', 'daily_checkin_hp', 'event_max_discount_pct',
  'exclusive_spin_free_delivery_cap', 'flash_discount_pct', 'free_delivery_threshold',
  'hof_induction_threshold', 'hp_bundle_min_purchase', 'hp_bundle_price_per_hp', 'hp_bundles',
  'hp_currency_name', 'hp_redeem_rate', 'hp_unlock_ceiling_pct',
  'leaderboard_prize_rank1_sides', 'leaderboard_prize_rank2_sides', 'leaderboard_prize_rank3_sides',
  'login_streak_hp', 'min_hp_redeem', 'min_topup_amount', 'min_withdrawal_amount',
  'monthly_hp_cap', 'notification_channels_critical', 'notification_channels_default',
  'order_lock_max_discount', 'order_streak_hp_rewards', 'paystack_preferred_bank',
  'social_share_hp', 'supabase_project_url', 'wallet_ref_prefix', 'platform_name', 'free_side_options',
]);
export const isLegacyStoredSetting = (key: string) => storedOnly.has(key);
