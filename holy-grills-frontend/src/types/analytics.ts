/**
 * Analytics contract — /api/analytics/* (analytics.py).
 * Every report returns an object; only `/analytics/export` returns raw text.
 */
import type { IsoDate } from './common';

/** Shared date-range query parameters accepted by the reporting endpoints. */
export interface AnalyticsParams {
  from_date?: IsoDate;
  to_date?: IsoDate;
  period?: string;
  campus_id?: string;
  [key: string]: unknown;
}

/** GET /api/analytics/sales. */
export interface SalesTrend {
  from_date?: IsoDate;
  to_date?: IsoDate;
  totals?: Record<string, unknown>;
  series?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

/** GET /api/analytics/hp. */
export interface HpAnalytics {
  from_date?: IsoDate;
  to_date?: IsoDate;
  earned?: number;
  spent?: number;
  [key: string]: unknown;
}

/** GET /api/analytics/referrals. */
export interface ReferralAnalytics {
  total_referrals?: number;
  top_referrers?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

/** GET /api/analytics/revenue. */
export interface RevenueAnalytics {
  revenue?: number;
  orders?: number;
  [key: string]: unknown;
}

/** GET /api/analytics/academic-calendar (B1). */
export interface AcademicCalendarAnalytics {
  academic_periods?: Array<Record<string, unknown>>;
  normal_day_baseline?: Record<string, unknown> | null;
  [key: string]: unknown;
}

/** GET /api/analytics/order-sources (B2). */
export interface OrderSourcesAnalytics {
  sources?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

/** GET /api/analytics/referral-network (A9). */
export interface ReferralNetworkAnalytics {
  nodes?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

/** GET /api/analytics/retention-ltv (A8). */
export interface RetentionLtvAnalytics {
  repeat_order_rate?: number;
  ltv?: number;
  cohorts?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

/** Brand partnership row (B4) — GET/POST/PATCH /api/analytics/brand-partnerships. */
export interface BrandPartnership {
  id?: string;
  brand_name?: string;
  contact_email?: string | null;
  status?: string;
  notes?: string | null;
  created_at?: string;
  [key: string]: unknown;
}

export interface BrandPartnershipPayload {
  brand_name: string;
  contact_email?: string;
  status?: string;
  notes?: string;
  [key: string]: unknown;
}

/** GET /api/analytics/export (raw CSV/plain text). */
export interface AnalyticsExportParams {
  type: string;
  [key: string]: unknown;
}
