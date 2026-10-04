/**
 * Delivery contract — /api/delivery/* (delivery.py).
 * The `/admin/*` sub-tree manages hostels and gates; the public reads are used
 * by checkout to price a delivery.
 */
import type { IsoDateTime, MutationResult, Naira, Uuid } from './common';

/** delivery_hostels row. */
export interface DeliveryHostel {
  id: Uuid;
  name: string;
  campus_id?: Uuid | null;
  zone?: string | null;
  delivery_fee?: Naira;
  is_active?: boolean;
  [key: string]: unknown;
}

/** delivery_gates row. */
export interface DeliveryGate {
  id: Uuid;
  name: string;
  campus_id?: Uuid | null;
  hostel_id?: Uuid | null;
  is_active?: boolean;
  /** Coordinates as documented at delivery.py:190 (lat/lon columns). */
  lat?: number | null;
  lon?: number | null;
  base_fee?: number | null;
  rate_per_km?: number | null;
  min_fee?: number | null;
  [key: string]: unknown;
}

export interface HostelPayload {
  name: string;
  zone?: string;
  delivery_fee?: number;
  campus_id?: Uuid;
  is_active?: boolean;
}

export interface GatePayload {
  name: string;
  hostel_id?: Uuid;
  campus_id?: Uuid;
  is_active?: boolean;
}

/** POST /api/delivery/calculate-fee request body. */
export interface CalculateFeePayload {
  hostel_id?: Uuid;
  gate_id?: Uuid;
  zone?: string;
  order_subtotal?: Naira;
  latitude?: number;
  longitude?: number;
  [key: string]: unknown;
}

/** POST /api/delivery/calculate-fee response. */
export interface DeliveryFeeResult extends MutationResult {
  delivery_fee?: Naira;
  estimated_minutes?: number;
  zone?: string;
  is_deliverable?: boolean;
}

/** GET /api/delivery/hostels + /gates wrappers. */
export interface DeliveryHostelsResponse {
  hostels: DeliveryHostel[];
  count?: number;
}

export interface DeliveryGatesResponse {
  gates: DeliveryGate[];
  count?: number;
}

export type DeliveryMutation = MutationResult & { created_at?: IsoDateTime };
