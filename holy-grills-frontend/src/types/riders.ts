/**
 * Rider contract — /api/riders/* (riders.py).
 */
import type { MutationResult, Naira, Uuid } from './common';
import type { Order } from './orders';

/** GET /api/riders/my-batch. */
export interface RiderBatch {
  batch: {
    id: Uuid;
    status?: string;
    batch_number?: number;
    [key: string]: unknown;
  } | null;
  orders: Order[];
  batches?: unknown[];
  other_batches?: number;
  sequencing_mode?: string;
}

/** GET /api/riders/stats. */
export interface RiderStats {
  deliveries_today?: number;
  deliveries_total?: number;
  earnings_today?: Naira;
  earnings_total?: Naira;
  rating?: number | null;
  is_available?: boolean;
  [key: string]: unknown;
}

/** GET /api/riders/earnings. */
export interface RiderEarnings {
  total?: Naira;
  this_week?: Naira;
  this_month?: Naira;
  entries?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

/** GET /api/riders/history. */
export interface RiderHistory {
  history: Order[];
  count?: number;
}

/** PATCH /api/riders/availability. */
export interface RiderAvailabilityPayload {
  is_available: boolean;
}

/** PATCH /api/riders/location (lat/lng update). */
export interface RiderLocationPayload {
  lat: number;
  lng: number;
}

/** POST /api/riders/orders/:id/pickup, /deliver, /attempt. */
export interface RiderOrderActionPayload {
  notes?: string;
  code?: string;
  [key: string]: unknown;
}

/** GET /api/riders/call/:order_id. */
export interface RiderCallLink {
  call_link: string;
}

export type RiderMutation = MutationResult;
