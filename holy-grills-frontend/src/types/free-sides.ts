/**
 * Free-side credits contract — /api/free-sides (free_sides.py).
 *
 * NOTE: the backend replaced the post-order `/redeem` flow with cart-stage
 * `/select` (credits are consumed at checkout). See §5 M2 of the Phase 0 audit.
 */
import type { IsoDateTime, MutationResult, Uuid } from './common';

/** A free-side credit grant (free_side_credits row). */
export interface FreeSideCredit {
  id?: Uuid;
  user_id?: Uuid;
  expires_at?: IsoDateTime | null;
  consumed_at?: IsoDateTime | null;
  reason?: string | null;
  [key: string]: unknown;
}

/** A selectable free-side item. */
export interface FreeSideItem {
  id: Uuid;
  name: string;
  image_url?: string | null;
  price?: number;
  is_active?: boolean;
  [key: string]: unknown;
}

/** GET /api/free-sides response. */
export interface FreeSidesStatus {
  total_credits?: number;
  credits?: FreeSideCredit[];
  available_sides?: FreeSideItem[];
  active_selections?: unknown[];
  [key: string]: unknown;
}

/** POST /api/free-sides/select request body (current backend flow). */
export interface SelectFreeSidePayload {
  free_side_item_id: Uuid;
  [key: string]: unknown;
}

/** POST /api/free-sides/redeem request body — legacy path, not implemented server-side. */
export interface RedeemFreeSidePayload {
  side_choice: Uuid | string;
  order_id?: Uuid;
}

/** POST /api/free-sides/admin/items + PATCH /admin/items/:id. */
export interface FreeSideItemPayload {
  name: string;
  price?: number;
  image_url?: string;
  is_active?: boolean;
}

/** POST /api/free-sides/admin/credits — grant credits to a user. */
export interface GrantFreeSideCreditsPayload {
  user_id: Uuid;
  credits?: number;
  validity_days?: number;
  reason?: string;
}

export type FreeSideMutation = MutationResult;
