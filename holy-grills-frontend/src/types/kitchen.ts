/**
 * Kitchen & stock contract — /api/kitchen/*, /api/measurement-units,
 * /api/admin/stock-items (kitchen.py: kitchen_bp, units_bp, stock_bp).
 */
import type { IsoDateTime, MutationResult, Uuid } from './common';
import type { Order } from './orders';

/** GET /api/kitchen/queue — orders the kitchen is working on. */
export type KitchenQueue = Order[];

/** GET /api/kitchen/windows — delivery windows for the batch view. */
export interface KitchenWindow {
  id: Uuid;
  label?: string;
  open_time?: string;
  close_time?: string;
  order_count?: number;
  [key: string]: unknown;
}

/** GET /api/kitchen/metrics. */
export interface KitchenMetrics {
  orders_today?: number;
  orders_completed?: number;
  avg_prep_minutes?: number;
  daily_order_capacity?: number | null;
  is_at_capacity?: boolean;
  [key: string]: unknown;
}

/** GET /api/kitchen/batch-summary/:window_id. */
export interface BatchSummary {
  window_id?: Uuid;
  summary?: Record<string, unknown> | unknown[];
  total_orders?: number;
}

/** GET/PATCH /api/kitchen/settings. */
export interface KitchenSetting {
  key: string;
  value: unknown;
  description?: string | null;
  updated_at?: IsoDateTime;
  [key: string]: unknown;
}

export interface KitchenSettingsResponse {
  settings: KitchenSetting[];
}

export interface UpdateKitchenSettingsPayload {
  settings?: Record<string, unknown>;
  [key: string]: unknown;
}

/** POST /api/kitchen/batch/:batch_id/advance. */
export interface AdvanceBatchPayload {
  status?: string;
  notes?: string;
}

/** GET /api/measurement-units. */
export interface MeasurementUnit {
  id: Uuid;
  name: string;
  abbreviation?: string | null;
  [key: string]: unknown;
}

/** stock_items row (/api/admin/stock-items). */
export interface StockItem {
  id: Uuid;
  name: string;
  unit?: string;
  quantity?: number;
  reorder_level?: number | null;
  purchase_unit_id?: Uuid | null;
  usage_unit_id?: Uuid | null;
  cost_per_unit?: number | null;
  [key: string]: unknown;
}

export interface StockItemPayload {
  name: string;
  unit?: string;
  quantity?: number;
  reorder_level?: number;
  purchase_unit_id?: Uuid;
  usage_unit_id?: Uuid;
  cost_per_unit?: number;
}

/** POST /api/admin/stock-items/:id/purchase + /usage. */
export interface StockMovementPayload {
  quantity: number;
  unit_cost?: number;
  notes?: string;
  recorded_at?: IsoDateTime;
  [key: string]: unknown;
}

/** GET /api/admin/stock-items/:id/ledger. */
export interface StockLedgerEntry {
  id?: Uuid;
  type?: 'purchase' | 'usage' | string;
  quantity?: number;
  notes?: string | null;
  created_at?: IsoDateTime;
  [key: string]: unknown;
}

export type StockMutation = MutationResult;
