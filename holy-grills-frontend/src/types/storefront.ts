/**
 * Storefront contract — /api/storefront/* (storefront.py) and the public
 * system-settings endpoint GET /api/storefront/config/public.
 */
import type { IsoDateTime, MutationResult, Uuid } from './common';

/** section_type enum (not constrained server-side — any string is accepted). */
export type StorefrontSectionType = 'hero' | 'banner' | 'promo' | 'faq' | string;

/** storefront_sections row (GET /api/storefront/sections). */
export interface StorefrontSection {
  id: Uuid;
  section_type?: StorefrontSectionType;
  title?: string | null;
  subtitle?: string | null;
  body?: string | null;
  image_url?: string | null;
  cta_label?: string | null;
  cta_url?: string | null;
  is_active?: boolean;
  display_order?: number;
  campus_id?: Uuid | null;
  [key: string]: unknown;
}

/** storefront_banners row (GET /api/storefront/banners). */
export interface StorefrontBanner {
  id: Uuid;
  title?: string | null;
  subtitle?: string | null;
  image_url?: string | null;
  link_url?: string | null;
  is_active?: boolean;
  display_order?: number;
  [key: string]: unknown;
}

/** storefront early supporter row. */
export interface EarlySupporter {
  id: Uuid;
  name?: string;
  role?: string | null;
  message?: string | null;
  photo_url?: string | null;
  amount?: number | null;
  [key: string]: unknown;
}

/** GET /api/storefront/operating-hours + the override endpoint. */
export interface OperatingHours {
  is_open?: boolean;
  open_time?: string;
  close_time?: string;
  days?: Record<string, unknown> | unknown[];
  override?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export interface OperatingHoursOverridePayload {
  date?: string;
  is_open?: boolean;
  open_time?: string;
  close_time?: string;
  reason?: string;
  [key: string]: unknown;
}

/** GET /api/storefront/config/public — public `system_settings` key/value map. */
export interface PublicConfig {
  whatsapp_support_number?: string | null;
  max_delivery_radius_km?: number;
  campus_lat?: number | null;
  campus_lon?: number | null;
  [key: string]: unknown;
}

/** POST /api/storefront/newsletter (subscribe) + /newsletter/unsubscribe. */
export interface NewsletterSubscribePayload {
  email: string;
  name?: string;
  [key: string]: unknown;
}

export interface NewsletterUnsubscribePayload {
  email?: string;
  token?: string;
}

/** Newsletter subscriber row (admin list). */
export interface NewsletterSubscriber {
  id: Uuid;
  email: string;
  subscribed_at?: IsoDateTime;
  unsubscribed_at?: IsoDateTime | null;
  [key: string]: unknown;
}

/** POST /api/storefront/newsletter/campaigns (+ /test, /:id/cancel). */
export interface NewsletterCampaignPayload {
  subject: string;
  body: string;
  audience?: string;
  scheduled_for?: IsoDateTime;
  [key: string]: unknown;
}

/** POST /api/storefront/promo-codes/validate. */
export interface ValidateStorefrontPromoPayload {
  code: string;
  [key: string]: unknown;
}

/** Admin payloads for sections/banners/supporters. */
export interface StorefrontSectionPayload {
  section_type: StorefrontSectionType;
  title?: string;
  subtitle?: string;
  body?: string;
  image_url?: string;
  cta_label?: string;
  cta_url?: string;
  is_active?: boolean;
  display_order?: number;
}

export interface StorefrontBannerPayload {
  title?: string;
  subtitle?: string;
  image_url?: string;
  link_url?: string;
  is_active?: boolean;
  display_order?: number;
}

export interface EarlySupporterPayload {
  name: string;
  role?: string;
  message?: string;
  photo_url?: string;
  amount?: number;
}

/** Image-update helper shared by sections/banners/supporters. */
export interface StorefrontImagePayload {
  image_url: string;
}

export type StorefrontMutation = MutationResult;
