/**
 * Rewards contract — /api/rewards/* (rewards.py).
 * Catalog reads return bare arrays; mutations return the created/updated row.
 */
import type { IsoDateTime, MutationResult, Uuid } from './common';

/** reward_category enum. */
export type RewardCategory = 'food' | 'merch' | 'experience' | 'marketplace';

/** redemption_status enum. */
export type RedemptionStatus = 'pending' | 'fulfilled' | 'rejected';

/** rewards row (GET /api/rewards). */
export interface Reward {
  id: Uuid;
  title: string;
  description?: string | null;
  hp_cost: number;
  category?: RewardCategory;
  image_url?: string | null;
  stock?: number | null;
  is_active?: boolean;
  flash_sale?: boolean;
  flash_discount_pct?: number | null;
  [key: string]: unknown;
}

export interface RewardRedemption {
  id: Uuid;
  reward_id?: Uuid;
  status: RedemptionStatus;
  hp_spent?: number;
  created_at?: IsoDateTime;
  fulfilled_at?: IsoDateTime | null;
  rejection_reason?: string | null;
  delivery_choice?: string | null;
  [key: string]: unknown;
}

/** POST /api/rewards/:id/redeem response. */
export interface RedeemRewardResult extends MutationResult {
  redemption?: RewardRedemption;
  redemption_id?: Uuid;
  status?: RedemptionStatus;
  hp_spent?: number;
  fulfilment_eta_hours?: number;
}

/**
 * POST /api/rewards/redemptions/:id/delivery-choice request body.
 * Backend reads only `delivery_mode` (rewards.py:865-878); the extra optional
 * fields are sent by RewardDeliveryModal for the instant flow and ignored.
 */
export interface RedemptionDeliveryChoicePayload {
  delivery_mode: 'instant' | 'next_order' | string;
  delivery_location_id?: string;
  delivery_type?: string;
  menu_item_id_for_reward?: string;
  [key: string]: unknown;
}

/** Admin create/update payloads — POST /api/rewards, PATCH /api/rewards/:id. */
export interface RewardPayload {
  title: string;
  hp_cost: number;
  category: RewardCategory;
  description?: string;
  image_url?: string;
  stock?: number | null;
  is_active?: boolean;
}

export type UpdateRewardPayload = Partial<RewardPayload>;

/** POST /api/rewards/:id/image. */
export interface RewardImagePayload {
  image_url: string;
}
