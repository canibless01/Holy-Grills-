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

/** An item inside POST /api/orders. */
export interface CreateOrderItem {
  menu_item_id: Uuid;
  quantity: number;
  addons?: Array<{ addon_option_id: Uuid }>;
}

/** Delivery address inside POST /api/orders. */
export interface CreateOrderAddress {
  address_line: string;
  landmark?: string;
  zone?: string;
}

/** POST /api/orders request body (guest checkout allowed). */
export interface CreateOrderPayload {
  items: CreateOrderItem[];
  delivery_window_id: Uuid;
  payment_method: PaymentMethod;
  delivery_address: CreateOrderAddress;
  hp_points_to_redeem?: number;
  promo_code?: string;
  is_scheduled?: boolean;
  scheduled_for_window_id?: Uuid;
  is_squad_order?: boolean;
  guest_name?: string;
  guest_phone?: string;
  paystack_reference?: string;
  wallet_amount?: number;
  [key: string]: unknown;
}

/** GET /api/orders query parameters. */
export interface OrderListParams {
  status?: OrderStatus;
  page?: number;
  per_page?: number;
  [key: string]: unknown;
}

/** Delivery window (GET /api/orders/delivery-windows). */
export interface DeliveryWindow {
  id: Uuid;
  label: string;
  open_time?: string;
  close_time?: string;
  is_open?: boolean;
  date?: IsoDate;
  [key: string]: unknown;
}

/** GET /api/orders/delivery-windows/status. */
export interface DeliveryWindowsStatus {
  is_open: boolean;
  message?: string;
  next_window?: DeliveryWindow | null;
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
