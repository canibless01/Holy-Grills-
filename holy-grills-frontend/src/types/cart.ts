/**
 * Cart contract — /api/cart (cart.py).
 * Cart rows are menu items plus quantity and resolved add-ons.
 */
import type { Naira, Uuid } from './common';
import type { AddonOption, MenuItem } from './menu';

/** cart_items row (item embedded when PostgREST joins menu_items). */
export interface CartItem {
  id: Uuid;
  menu_item_id: Uuid;
  quantity: number;
  unit_price?: Naira;
  line_total?: Naira;
  addons?: Array<AddonOption | { addon_option_id: Uuid }>;
  menu_item?: MenuItem | null;
  name_snapshot?: string;
  [key: string]: unknown;
}

/** GET /api/cart response. */
export interface Cart {
  items?: CartItem[];
  cart_items?: CartItem[];
  subtotal?: Naira;
  delivery_fee?: Naira;
  total?: Naira;
  item_count?: number;
  [key: string]: unknown;
}

/** POST /api/cart request body. */
export interface AddToCartPayload {
  menu_item_id: Uuid;
  quantity: number;
  addons?: Array<{ addon_option_id: Uuid }>;
  [key: string]: unknown;
}

/** PATCH /api/cart/:item_id request body (quantity 0 removes the row). */
export interface UpdateCartItemPayload {
  quantity: number;
  addons?: Array<{ addon_option_id: Uuid }>;
  [key: string]: unknown;
}
