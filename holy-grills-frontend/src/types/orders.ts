/**
 * Order contract — /api/orders/* (orders.py).
 *
 * Endpoints return the order object **bare** (POST /orders, GET /orders/:id) or
 * a bare/`orders`-keyed list (GET /orders). `liveApi.normOrder()` normalises both
 * into `Order` (order_items + delivery_address + delivery_window + total_amount),
 * which is the shape every page consumes.
 */
import type { IsoDate, IsoDateTime, MutationResult, Naira, Uuid } from './common';
import type { AddonOption } from './menu';

/** Order status enum (API_FIELD_REFERENCE.md Enum Master List). */
export type OrderStatus =
  | 'received'
  | 'preparing'
  | 'ready'
  | 'assigned'
  | 'out_for_delivery'
  | 'delivered'
  | 'cancelled'
  | 'refunded'
  | 'delivery_attempted'
  | 'unclaimed';

/** Payment method enum. */
export type PaymentMethod = 'wallet' | 'card' | 'split';

/** order_items row (name_snapshot is added by the normaliser). */
export interface OrderItem {
  id?: Uuid;
  order_id?: Uuid;
  menu_item_id?: Uuid;
  name_snapshot?: string;
  name?: string;
  quantity: number;
  unit_price?: Naira;
  price?: Naira;
  line_total?: Naira;
  addons?: Array<AddonOption | { addon_option_id: Uuid }>;
  [key: string]: unknown;
}

/** Address attached to an order (`line1` is produced by the normaliser). */
export interface OrderDeliveryAddress {
  line1?: string;
  address_line?: string;
  landmark?: string | null;
  zone?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  [key: string]: unknown;
}

/** Delivery window attached to an order. */
export interface OrderDeliveryWindow {
  id?: Uuid;
  label?: string;
  open_time?: string;
  close_time?: string;
  date?: IsoDate | string;
  [key: string]: unknown;
}

/** Delivery batch (kitchen → rider hand-off). */
export interface DeliveryBatch {
  id?: Uuid;
  status?: string;
  batch_number?: number;
  [key: string]: unknown;
}

/** Order as returned by the API and normalised by liveApi. */
export interface Order {
  id: Uuid;
  user_id?: Uuid | null;
  status: OrderStatus;
  order_items?: OrderItem[];
  items?: OrderItem[];
  subtotal?: Naira;
  delivery_fee?: Naira;
  discount_amount?: Naira;
  total_amount?: Naira;
  total?: Naira;
  payment_method?: PaymentMethod;
  payment_status?: string;
  hp_points_used?: number;
  hp_earned?: number;
  delivery_address?: OrderDeliveryAddress | null;
  delivery_window?: OrderDeliveryWindow | null;
  delivery_batch?: DeliveryBatch | null;
  is_squad_order?: boolean;
  is_scheduled?: boolean;
  scheduled_for?: IsoDateTime | null;
  guest_name?: string | null;
  guest_phone?: string | null;
  guest_email?: string | null;
  created_at?: IsoDateTime;
  updated_at?: IsoDateTime;
  [key: string]: unknown;
}

/** Normalised order (what `liveApi.orders.get()` returns). */
export type NormalisedOrder = Order & {
  order_items: OrderItem[];
  items: OrderItem[];
  total_amount: Naira;
};

/**
 * An item inside POST /api/orders, as the storefront sends it (Checkout.tsx) —
 * `notes`, variations and add-ons are all optional per line.
 */
export interface CreateOrderItem {
  menu_item_id: Uuid;
  quantity: number;
  notes?: string;
  selected_variations?: Array<{ option_id: Uuid }>;
  selected_addons?: Array<{ addon_id: Uuid; quantity: number }>;
  addons?: Array<{ addon_id: Uuid; quantity?: number }>;
}

/**
 * POST /api/orders request body (guest checkout allowed).
 *
 * Retyped against the live caller: the previous shape required a
 * `delivery_window_id` and an object `delivery_address`, while Checkout sends a
 * window only when the order is scheduled and a *string* address for off-campus
 * deliveries — which is why the caller used `Record<string, any>` instead. Only
 * `items` and `payment_method` are always present.
 */
export interface CreateOrderPayload {
  items: CreateOrderItem[];
  payment_method: PaymentMethod;
  /** 'website' | 'pwa' | … — mirrored from sessionStorage. */
  order_source?: string;
  delivery_type?: string;
  promo_code?: string;
  squad_id?: Uuid;
  excluded_member_ids?: Array<Uuid>;
  extra_members?: unknown[];
  notes?: string;
  wallet_amount?: number;
  guest_name?: string;
  guest_phone?: string;
  guest_email?: string;
  delivery_location_id?: Uuid;
  delivery_location_lat?: number;
  delivery_location_lon?: number;
  delivery_address?: string;
  addons?: Array<{ addon_id: Uuid; quantity: number }>;
  delivery_window_id?: Uuid;
  is_scheduled?: boolean;
  /**
   * Let the backend place the order in the next bookable slot when the current
   * window is closed or full. Set by the capacity flow AND by checkout's
   * "Schedule my order" button — the backend then searches from TODAY, so a
   * kitchen that has not opened yet schedules for today's opening.
   */
  accept_next_available_date?: boolean;
  hp_points_to_redeem?: number;
  scheduled_for_window_id?: Uuid;
  is_squad_order?: boolean;
  paystack_reference?: string;
  [key: string]: unknown;
}

/** POST /api/delivery/calculate-fee request body (Checkout's pin/gate flow). */
export interface CalculateDeliveryFeePayload {
  delivery_type: string;
  lat: number;
  lon: number;
  /** Set once a gate is pinned or kept from an earlier calculation. */
  delivery_location_id?: Uuid;
}

/** GET /api/orders query parameters. */
export interface OrderListParams {
  status?: OrderStatus;
  page?: number;
  per_page?: number;
  [key: string]: unknown;
}

/**
 * Delivery window (GET /api/orders/delivery-windows). The scheduling UI also
 * reads the capacity/slot fields the same endpoint attaches to each window
 * (`is_closed`/`is_full` are what ScheduleOrderPanel filters on).
 */
export interface DeliveryWindow {
  id: Uuid;
  label: string;
  open_time?: string;
  close_time?: string;
  is_open?: boolean;
  date?: IsoDate;
  is_closed?: boolean;
  is_full?: boolean;
  /** True only while this window is bookable right now (open, not full, in hours). */
  is_open_now?: boolean;
  starts_at?: string | null;
  delivery_starts_at?: string | null;
  delivery_ends_at?: string | null;
  remaining?: number | null;
  [key: string]: unknown;
}

/**
 * GET /api/orders/delivery-windows/status.
 *
 * `is_open` is tri-state at the source: `null` means "not known yet" (no campus
 * chosen), which the UI must never render as closed — see KitchenStatusBox.
 * `next_available_date`/`next_opens_at` are the schedule hints
 * ScheduleOrderPanel turns into the next-opening countdown.
 */
export interface DeliveryWindowsStatus {
  is_open?: boolean | null;
  /**
   * Why ordering is unavailable right now: 'before_opening' | 'after_closing' |
   * 'closed_today' | 'full' | 'open' | 'no_window'. Absent on older backends.
   */
  reason?: string | null;
  message?: string;
  next_window?: DeliveryWindow | null;
  next_available_date?: string | null;
  next_opens_at?: string | null;
  first_open_window?: DeliveryWindow | null;
  windows?: DeliveryWindow[];
  [key: string]: unknown;
}

/** Delivery zone (GET /api/orders/delivery-zones). */
export interface DeliveryZone {
  id?: Uuid;
  name: string;
  delivery_fee: Naira;
  estimated_minutes?: number;
  [key: string]: unknown;
}

/** PATCH /api/orders/:id/status + POST /api/orders/:id/walk. */
export interface UpdateOrderStatusPayload {
  status?: OrderStatus;
  target_status?: OrderStatus;
  notes?: string;
}

/** POST /api/orders/:id/cancel. */
export interface CancelOrderPayload {
  reason?: string;
}

/** POST /api/orders/:id/review (order must be delivered). */
export interface ReviewOrderPayload {
  rating: number;
  kitchen_rating?: number;
  rider_rating?: number;
  comment?: string;
}

/** POST /api/orders/:id/review/images. */
export interface ReviewImagesPayload {
  image_urls: string[];
}

/** POST /api/orders/:id/squad-members. */
export interface AddSquadMembersPayload {
  emails: string[];
}

/** POST /api/orders/:id/resend-tracking { guest_email } — see §5 of the Phase 0 audit. */
export interface ResendTrackingPayload {
  guest_email: string;
}

/** POST /api/orders/validate-promo request/response. */
export interface ValidatePromoPayload {
  code: string;
  subtotal?: number;
  [key: string]: unknown;
}

export interface PromoValidation {
  valid: boolean;
  discount_amount?: Naira;
  discount_type?: 'percentage' | 'flat';
  message?: string;
  [key: string]: unknown;
}

/** GET /api/orders/active — `{ order }` or `{ order: null }`. */
export interface ActiveOrderResponse {
  order: Order | null;
}

/** GET /api/orders/scheduled. */
export interface ScheduledOrdersResponse {
  scheduled_orders: Order[];
  count: number;
}

/** GET /api/orders/suggestions. */
export interface OrderSuggestion {
  order_id?: Uuid;
  ordered_at?: IsoDateTime;
  items?: Array<{ name: string; quantity: number }>;
}

export interface OrderSuggestionResponse {
  suggestion: OrderSuggestion | null;
}

/** GET /api/orders/:id/call-rider. */
export interface CallRiderResponse {
  rider: { name: string; call_link: string } | null;
}

/** GET /api/orders/:id/history — status log entries. */
export interface OrderHistoryEntry {
  id?: Uuid;
  status: OrderStatus;
  notes?: string | null;
  created_at?: IsoDateTime;
  [key: string]: unknown;
}

/** Per-order squad member row (GET /api/orders/:id/squad-members). */
export interface OrderSquadMember {
  id: Uuid;
  email?: string;
  full_name?: string;
  status?: 'pending' | 'joined' | 'declined' | string;
  [key: string]: unknown;
}

export type OrderMutation = MutationResult;
