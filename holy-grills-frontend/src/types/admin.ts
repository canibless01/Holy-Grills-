/**
 * Admin contract — /api/admin/* (admin.py, admin_gifts.py,
 * admin_feature_flags.py) plus the rider-payment admin helpers in riders.py.
 *
 * NOTE: three frontend paths in this domain do not exist server-side
 * (`/admin/gifts/settings`, `/admin/gifts/first-order-gifts`,
 * `/admin/free-credits`, `/admin/exclusive-spin/history`). See Phase 0 audit §5.
 */
import type { IsoDate, IsoDateTime, MutationResult, Naira, Uuid } from './common';
import type { HpTransaction } from './hp';
import type { WalletTransaction } from './wallet';
import type { UserRole } from './auth';

/** profiles row as returned by GET /api/admin/users. */
export interface AdminUser {
  id: Uuid;
  email: string;
  full_name: string;
  phone?: string | null;
  role: UserRole;
  campus_id?: Uuid | null;
  is_active?: boolean;
  created_at?: IsoDateTime;
  [key: string]: unknown;
}

export interface AdminUsersParams {
  role?: UserRole;
  campus_id?: Uuid;
  q?: string;
  limit?: number;
  offset?: number;
  [key: string]: unknown;
}

/** GET /api/admin/users/:id — profile + related counters. */
export interface AdminUserDetail extends AdminUser {
  hp_balance?: { active?: number; pending?: number; total?: number } | null;
  wallet_balance?: Naira;
  orders_count?: number;
}

/** PATCH /api/admin/users/:id/role. */
export interface UpdateUserRolePayload {
  role: UserRole;
}

/** Normalised HP view built by liveApi.admin.getUserHp(). */
export interface AdminUserHp {
  total: number;
  active: number;
  pending: number;
  tier: unknown;
  tier_multiplier: number | null;
  transactions: HpTransaction[];
}

/** GET /api/admin/users/:id/wallet. */
export interface AdminUserWallet {
  balance?: Naira;
  transactions?: WalletTransaction[];
  [key: string]: unknown;
}

/** POST /api/admin/hp/bulk-grant. */
export interface BulkGrantHpPayload {
  user_ids?: Uuid[];
  amount: number;
  reason?: string;
  campus_id?: Uuid;
  [key: string]: unknown;
}

/** POST /api/hp/admin/grant + /api/hp/admin/expire. */
export interface AdminHpAdjustmentPayload {
  user_id?: Uuid;
  amount: number;
  reason?: string;
  [key: string]: unknown;
}

/** GET /api/admin/hp/report. */
export interface HpReport {
  totals?: Record<string, unknown>;
  rows?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

/** admin delivery_windows row (GET /api/admin/delivery-windows). */
export interface AdminDeliveryWindow {
  id: Uuid;
  label?: string;
  open_time?: string;
  close_time?: string;
  date?: IsoDate;
  is_open?: boolean;
  capacity?: number | null;
  orders_placed?: number;
  [key: string]: unknown;
}

export interface AdminDeliveryWindowPayload {
  label?: string;
  open_time?: string;
  close_time?: string;
  date?: IsoDate;
  capacity?: number | null;
  [key: string]: unknown;
}

/** ordering_windows row (GET /api/admin/ordering-windows). */
export interface OrderingWindow {
  id: Uuid;
  day_of_week?: number | null;
  date?: IsoDate | null;
  open_time?: string;
  close_time?: string;
  capacity?: number | null;
  is_active?: boolean;
  [key: string]: unknown;
}

export interface OrderingWindowPayload {
  day_of_week?: number;
  date?: IsoDate;
  open_time?: string;
  close_time?: string;
  capacity?: number | null;
  is_active?: boolean;
  [key: string]: unknown;
}

/** delivery_batches row (GET /api/admin/delivery-batches). */
export interface AdminDeliveryBatch {
  id: Uuid;
  batch_number?: number;
  status?: 'pending' | 'active' | 'completed' | 'cancelled' | string;
  rider_id?: Uuid | null;
  rider_pay_total?: Naira | null;
  order_count?: number;
  window_id?: Uuid | null;
  created_at?: IsoDateTime;
  [key: string]: unknown;
}

export interface AdminDeliveryBatchPayload {
  window_id?: Uuid;
  rider_id?: Uuid;
  order_ids?: Uuid[];
  status?: string;
  [key: string]: unknown;
}

/** promo_codes row (GET /api/admin/promo-codes). */
export interface PromoCode {
  id: Uuid;
  code: string;
  discount_type?: 'percentage' | 'flat';
  discount_value?: number;
  scope?: 'cart' | 'item';
  is_active?: boolean;
  max_uses?: number | null;
  uses_count?: number;
  expires_at?: IsoDateTime | null;
  [key: string]: unknown;
}

export interface PromoCodePayload {
  code: string;
  discount_type: 'percentage' | 'flat';
  discount_value: number;
  scope?: 'cart' | 'item';
  is_active?: boolean;
  max_uses?: number | null;
  expires_at?: IsoDateTime | null;
  [key: string]: unknown;
}

/** GET /api/admin/promo-codes/:id/uses. */
export interface PromoCodeUses {
  promo_code?: PromoCode;
  total_uses?: number;
  total_discount_given?: Naira;
  uses?: Array<Record<string, unknown>>;
}

/** GET /api/admin/abandoned-carts. */
export interface AbandonedCart {
  id: Uuid;
  user_id?: Uuid | null;
  full_name?: string | null;
  phone?: string | null;
  item_count?: number;
  subtotal?: Naira;
  last_activity_at?: IsoDateTime;
  [key: string]: unknown;
}

/** GET /api/admin/audit-log. */
export interface AuditLogEntry {
  id: Uuid;
  actor_id?: Uuid | null;
  actor_role?: string | null;
  entity_type?: string;
  entity_id?: string;
  action?: string;
  before_value?: unknown;
  after_value?: unknown;
  campus_id?: Uuid | null;
  created_at?: IsoDateTime;
  [key: string]: unknown;
}

export interface AuditLogParams {
  entity_type?: string;
  actor_id?: Uuid;
  limit?: number;
  offset?: number;
  [key: string]: unknown;
}

/** GET /api/admin/cron/status (live shape: { checked_at, jobs: {…}, summary }). */
export interface CronJobStatus {
  job: string;
  status?: string;
  last_triggered?: IsoDateTime | null;
  cadence?: string;
  desc?: string;
  [key: string]: unknown;
}

export interface CronStatusResponse {
  checked_at?: IsoDateTime;
  jobs?: Record<string, unknown> | CronJobStatus[];
  cron_jobs?: CronJobStatus[];
  summary?: Record<string, unknown>;
}

/** system_settings row (GET /api/admin/settings). */
export interface SystemSetting {
  id?: Uuid;
  key: string;
  value: unknown;
  description?: string | null;
  is_public?: boolean;
  campus_id?: Uuid | null;
  updated_at?: IsoDateTime;
  [key: string]: unknown;
}

export interface SystemSettingPayload {
  key: string;
  value: unknown;
  description?: string;
  campus_id?: Uuid | null;
  [key: string]: unknown;
}

/** First-order gift settings slice (admin onboarding). */
export interface GiftSettings {
  first_order_gift_enabled?: boolean;
  launch_window_end_date?: IsoDate | null;
  first_order_gift_item_name?: string | null;
  [key: string]: unknown;
}

/** first_order_gifts row (admin list). */
export interface FirstOrderGift {
  id: Uuid;
  user_id?: Uuid;
  full_name?: string | null;
  phone?: string | null;
  status?: 'pending' | 'claimed' | 'returned' | string;
  item_name?: string | null;
  created_at?: IsoDateTime;
  [key: string]: unknown;
}

export interface UpdateGiftStatusPayload {
  status: string;
  notes?: string;
}

/** reviews row (GET /api/admin/reviews). */
export interface AdminReview {
  id: Uuid;
  order_id?: Uuid;
  user_id?: Uuid;
  full_name?: string | null;
  rating?: number;
  comment?: string | null;
  is_promoted?: boolean;
  created_at?: IsoDateTime;
  [key: string]: unknown;
}

/** admin_campuses row (GET /api/admin/campuses). */
export interface AdminCampus {
  id: Uuid;
  name: string;
  slug?: string;
  lat?: number | null;
  lon?: number | null;
  is_active?: boolean;
  [key: string]: unknown;
}

export interface CampusLocationPayload {
  lat: number;
  lon: number;
}

/** rider roster entry (GET /api/riders/roster). */
export interface RiderRosterEntry {
  rider_id: Uuid;
  full_name?: string;
  phone?: string | null;
  campus_id?: Uuid | null;
  is_available?: boolean;
  availability_updated_at?: IsoDateTime | null;
  location_lat?: number | null;
  location_lng?: number | null;
  location_updated_at?: IsoDateTime | null;
  active_batches?: number;
  [key: string]: unknown;
}

/** Rider payment summary (GET /api/riders/admin/payments). */
export interface RiderPayment {
  rider_id: Uuid;
  full_name?: string;
  earnings?: Naira;
  paid?: Naira;
  outstanding?: Naira;
  [key: string]: unknown;
}

export interface SetBatchPayPayload {
  rider_pay_total: Naira;
}

export interface MarkBatchesPaidPayload {
  batch_ids: Uuid[];
}

export interface MarkBatchesPaidResult extends MutationResult {
  updated?: number;
  skipped?: number;
  not_found?: number;
}

/** GET /api/admin/webhook-events. */
export interface WebhookEvent {
  id: Uuid;
  provider?: string;
  event_type?: string;
  status?: string;
  payload?: unknown;
  created_at?: IsoDateTime;
  [key: string]: unknown;
}

export interface WebhookEventsParams {
  provider?: string;
  status?: string;
  from_date?: IsoDate;
  to_date?: IsoDate;
  campus_id?: Uuid;
  limit?: number;
  offset?: number;
  [key: string]: unknown;
}

/** feature_flags row (GET /api/admin/feature-flags). */
export interface FeatureFlag {
  id?: Uuid;
  name: string;
  is_enabled: boolean;
  description?: string | null;
  campus_id?: Uuid | null;
  rollout_percentage?: number | null;
  [key: string]: unknown;
}

export interface FeatureFlagPayload {
  name: string;
  is_enabled?: boolean;
  description?: string;
  rollout_percentage?: number | null;
}

/** POST /api/upload/signature — signed Cloudinary upload params (uploads.py). */
export interface UploadSignature {
  signature: string;
  timestamp: number;
  api_key: string;
  cloud_name: string;
  folder?: string;
  [key: string]: unknown;
}

/** GET /api/admin/leaderboard-prizes + PATCH /:id (admin_feature_flags.py). */
export interface LeaderboardPrize {
  id: string;
  user_id?: Uuid;
  full_name?: string | null;
  rank?: number | null;
  period_key?: string | null;
  status?: 'pending' | 'fulfilled' | 'cancelled' | string;
  notes?: string | null;
  [key: string]: unknown;
}

/** GET /api/admin/hall-of-fame-rewards + PATCH /:id (admin_feature_flags.py). */
export interface HallOfFameReward {
  id: string;
  user_id?: Uuid;
  full_name?: string | null;
  period_key?: string | null;
  status?: 'pending' | 'fulfilled' | 'cancelled' | string;
  notes?: string | null;
  [key: string]: unknown;
}

/** PATCH payload shared by both fulfilment queues. */
export interface FulfilmentStatusPayload {
  status: 'pending' | 'fulfilled' | 'cancelled';
  notes?: string;
}

/** Admin free-side credit row (GET /admin/free-credits — no backend route yet). */
export interface FreeSideCreditAdminRow {
  user_id?: Uuid;
  full_name?: string | null;
  credits?: number;
  expires_at?: IsoDateTime | null;
  [key: string]: unknown;
}
