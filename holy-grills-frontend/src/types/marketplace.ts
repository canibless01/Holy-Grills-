/**
 * Marketplace contract — /api/marketplace/* (marketplace.py).
 */
import type { IsoDateTime, MutationResult, Naira, Uuid } from './common';
import type { PaymentMethod } from './orders';

/** listing_type enum. */
export type ListingType = 'code' | 'service' | 'product' | 'experience';

/** listing_status enum. */
export type ListingStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'draft'
  | 'active'
  | 'archived';

/** marketplace_listings row. */
export interface MarketplaceListing {
  id: Uuid;
  title: string;
  description?: string | null;
  listing_type?: ListingType;
  price: Naira;
  hp_price?: number | null;
  image_url?: string | null;
  status?: ListingStatus;
  is_active?: boolean;
  stock?: number | null;
  vendor_id?: Uuid | null;
  vendor_name?: string | null;
  created_at?: IsoDateTime;
  [key: string]: unknown;
}

/** GET /api/marketplace query parameters. */
export interface MarketplaceListParams {
  category?: ListingType;
  page?: number;
  per_page?: number;
  [key: string]: unknown;
}

/** POST /api/marketplace/listings/:id/purchase request body (marketplace.py:259). */
export interface PurchaseListingPayload {
  payment_method: PaymentMethod;
  /** Opt into the HP discount (never a standalone payment method). */
  use_hp?: boolean;
  /** Portion paid from the wallet when payment_method is 'split'. */
  wallet_amount?: number;
  [key: string]: unknown;
}

/** marketplace_purchases row (GET /api/marketplace/purchases). */
export interface MarketplacePurchase {
  id: Uuid;
  listing_id?: Uuid;
  buyer_id?: Uuid;
  amount?: Naira;
  hp_spent?: number;
  status?: string;
  code?: string | null;
  created_at?: IsoDateTime;
  listing?: MarketplaceListing | null;
  [key: string]: unknown;
}

/** POST /api/marketplace/:id/purchase response. */
export interface PurchaseListingResult extends MutationResult {
  purchase?: MarketplacePurchase;
  code?: string | null;
  listing?: MarketplaceListing;
}

/** POST /api/marketplace/requests — vendor request (public). */
export interface MarketplaceRequestPayload {
  vendor_name: string;
  vendor_email: string;
  service_title: string;
  category: string;
  description: string;
  proposed_price?: number;
}

/** POST /api/marketplace/purchases/:id/report. */
export interface ReportPurchasePayload {
  reason: string;
  details?: string;
}

/** Admin: POST /api/marketplace/admin/listings. */
export interface AdminListingPayload {
  title: string;
  listing_type: ListingType;
  price: number;
  description?: string;
  hp_price?: number;
  image_url?: string;
  is_active?: boolean;
  vendor_id?: Uuid;
}

/** Admin: POST /api/marketplace/admin/codes/:listing_id. */
export interface UploadListingCodesPayload {
  codes: string[];
}

/** Admin: POST /api/marketplace/listings/:id/image (no /admin segment on the route). */
export interface ListingImagePayload {
  image_url: string;
}

/**
 * Admin: PATCH /api/marketplace/admin/listings/:id/availability.
 * The route accepts exactly these fields (marketplace.py:935) plus campus_id.
 */
export interface ListingAvailabilityPayload {
  inventory_count?: number;
  low_inventory_threshold?: number;
  is_out_of_stock?: boolean;
  price_override?: number;
  campus_id?: string;
}
