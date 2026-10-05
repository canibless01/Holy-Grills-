/**
 * Exclusive spin contract — /api/exclusive-spin (exclusive_spin.py) and its
 * admin prize pool (admin.py /api/admin/exclusive-spin-pool).
 */
import type { IsoDateTime, MutationResult, Uuid } from './common';

/** A prize-pool entry (odds template item). */
export interface ExclusiveSpinPrize {
  id: Uuid;
  label?: string;
  prize_type?: string;
  weight?: number;
  value?: number;
  hp_amount?: number;
  campus_id?: Uuid | null;
  is_active?: boolean;
  [key: string]: unknown;
}

/** GET /api/exclusive-spin — spin availability + pool summary. */
export interface ExclusiveSpinStatus {
  spins_available?: number;
  credits?: number;
  extra_cost_hp?: number;
  prizes?: ExclusiveSpinPrize[];
  [key: string]: unknown;
}

/** POST /api/exclusive-spin/spin response. */
export interface ExclusiveSpinResult extends MutationResult {
  prize?: ExclusiveSpinPrize | null;
  hp_won?: number;
  spins_remaining?: number;
}

/** Admin: GET /api/admin/exclusive-spin-pool response item (same entity). */
export type ExclusiveSpinTemplateItem = ExclusiveSpinPrize;

/** Admin: POST/PATCH prize-pool payload. */
export interface ExclusiveSpinPrizePayload {
  label?: string;
  prize_type?: string;
  weight?: number;
  hp_amount?: number;
  value?: number;
  campus_id?: Uuid | null;
  is_active?: boolean;
}

/** Admin: fulfilment record (GET /api/admin/exclusive-spin-prizes). */
export interface ExclusiveSpinPrizeFulfilment {
  id: Uuid;
  user_id?: Uuid;
  prize?: string;
  status?: 'pending' | 'fulfilled' | 'cancelled' | string;
  notes?: string | null;
  created_at?: IsoDateTime;
  [key: string]: unknown;
}
