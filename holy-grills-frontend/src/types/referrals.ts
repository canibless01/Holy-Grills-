/**
 * Referrals contract — /api/referrals/* (referrals.py).
 */
import type { MutationResult, Uuid } from './common';

/** A referral milestone entry (GET /api/referrals). */
export interface ReferralMilestone {
  count: number;
  hp_bonus: number;
  achieved: boolean;
}

/** GET /api/referrals (bare object) and GET /api/referrals/stats. */
export interface ReferralStats {
  referral_code?: string | null;
  total_referrals: number;
  total_hp_earned?: number;
  milestones?: ReferralMilestone[];
  pending?: number;
  referred_friends?: ReferredFriend[];
  [key: string]: unknown;
}

/** One referred friend row. */
export interface ReferredFriend {
  id?: Uuid;
  full_name?: string;
  joined_at?: string;
  status?: string;
  hp_awarded?: number;
  [key: string]: unknown;
}

/** POST /api/referrals/complete request body (internal/admin). */
export interface CompleteReferralPayload {
  referred_user_id: Uuid;
  order_id?: Uuid;
}

export type ReferralMutation = MutationResult;
