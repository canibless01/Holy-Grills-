/**
 * Holy Points contract — /api/hp/* (hp.py).
 * Numbers follow API_FIELD_REFERENCE.md §Holy Points (earn 0.1 HP/₦1, etc.).
 */
import type { IsoDateTime, MutationResult, Uuid } from './common';

/** hp_transaction_type enum. */
export type HpTransactionType =
  | 'earned'
  | 'spent'
  | 'expired'
  | 'transferred_in'
  | 'transferred_out'
  | 'pending'
  | 'unlocked';

/** GET /api/hp/balance. */
export interface HpBalance {
  active: number;
  pending: number;
  total: number;
  pending_ceiling?: number;
  tier?: { name: string; multiplier: number } | null;
  /** HP earned in the trailing 120 days — drives tier progress (hp_service.py:58). */
  hp_earned_120day?: number;
  [key: string]: unknown;
}

/** hp_transactions row (GET /api/hp/transactions). */
export interface HpTransaction {
  id: Uuid;
  amount: number;
  type: HpTransactionType;
  description?: string | null;
  reference_id?: Uuid | null;
  created_at?: IsoDateTime;
  [key: string]: unknown;
}

/** GET /api/hp/transactions query parameters. */
export interface HpTransactionsParams {
  page?: number;
  per_page?: number;
  type?: HpTransactionType;
  [key: string]: unknown;
}

/** GET /api/hp/tiers — tier ladder with multipliers. */
export interface HpTier {
  id?: Uuid;
  name: string;
  slug?: string;
  min_hp?: number;
  multiplier?: number;
  hp_multiplier?: number;
  perks?: string[];
  [key: string]: unknown;
}

/** POST /api/hp/transfer request body. */
export interface TransferHpPayload {
  recipient_id: Uuid;
  amount: number;
  notes?: string;
}

/** GET /api/hp/unlock-history. */
export interface HpUnlockEntry {
  id?: Uuid;
  amount?: number;
  unlocked_at?: IsoDateTime;
  [key: string]: unknown;
}

/** GET /api/hp/bundles — purchasable HP bundles. */
export interface HpBundle {
  id?: Uuid;
  hp_amount: number;
  price: number;
  label?: string;
  [key: string]: unknown;
}

/** POST /api/hp/bundles/purchase request body. */
export interface PurchaseHpBundlePayload {
  hp_amount: number;
  paystack_reference: string;
}

export type HpMutation = MutationResult;
