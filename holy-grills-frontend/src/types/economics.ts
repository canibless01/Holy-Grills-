/**
 * Economics dashboard contract — /api/admin/economics/* (admin_economics.py,
 * services/economics_dashboard_service.py).
 */
import type { IsoDate, Naira, Uuid } from './common';

export interface EconomicsParams {
  from_date?: IsoDate;
  to_date?: IsoDate;
  campus_id?: Uuid;
  period?: string;
  [key: string]: unknown;
}

/** GET /api/admin/economics/overview. */
export interface EconomicsOverview {
  revenue?: Naira;
  cost?: Naira;
  margin?: Naira;
  margin_pct?: number;
  hp_liability?: Naira;
  [key: string]: unknown;
}

/** One row of GET /api/admin/economics/tier-breakdown. */
export interface EconomicsTierBreakdown {
  tier?: string;
  users?: number;
  revenue?: Naira;
  hp_issued?: number;
  hp_liability?: Naira;
  [key: string]: unknown;
}

/** GET /api/admin/economics/redemption-analytics. */
export interface EconomicsRedemptionAnalytics {
  redemptions?: number;
  hp_redeemed?: number;
  by_category?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}
