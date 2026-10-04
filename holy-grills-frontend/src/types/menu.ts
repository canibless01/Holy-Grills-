/**
 * Menu contract — /api/menu/* (menu.py).
 * Entities follow API_FIELD_REFERENCE.md §Menu; admin payloads follow
 * menu.py's create/update handlers.
 */
import type { Naira, Uuid } from './common';

/** menu_categories row. */
export interface MenuCategory {
  id: Uuid;
  name: string;
  slug: string;
  description?: string | null;
  image_url?: string | null;
  is_active?: boolean;
  display_order?: number;
  campus_id?: Uuid | null;
  [key: string]: unknown;
}

/** Add-on option: { id, name, price_delta }. */
export interface AddonOption {
  id: Uuid;
  name: string;
  price_delta: number;
  is_available?: boolean;
  [key: string]: unknown;
}

/** Add-on group attached to an item (min/max selectable options). */
export interface AddonGroup {
  id: Uuid;
  name: string;
  min_select: number;
  max_select: number;
  is_required?: boolean;
  options: AddonOption[];
  [key: string]: unknown;
}

/** Standalone add-on row (GET /api/menu/addons). */
export interface MenuAddon {
  id: Uuid;
  name: string;
  price: number;
  price_delta?: number;
  is_available?: boolean;
  is_archived?: boolean;
  [key: string]: unknown;
}

/** menu_item_variation_options row. */
export interface VariationOption {
  id: Uuid;
  name: string;
  price_delta?: number;
  is_available?: boolean;
  [key: string]: unknown;
}

/** menu_item_variation_groups row (the active customisation mechanism — see menu.py header). */
export interface VariationGroup {
  id: Uuid;
  name: string;
  min_select?: number;
  max_select?: number;
  is_required?: boolean;
  options?: VariationOption[];
  [key: string]: unknown;
}

/** menu_items row as returned by GET /api/menu/items. */
export interface MenuItem {
  id: Uuid;
  name: string;
  description?: string | null;
  price: Naira;
  hp_earn_value?: number;
  hp_multiplier?: number;
  image_url?: string | null;
  category_id?: Uuid | null;
  category?: { name?: string; slug?: string } | null;
  is_available?: boolean;
  is_sold_out?: boolean;
  is_featured?: boolean;
  is_secret?: boolean;
  is_archived?: boolean;
  daily_order_capacity?: number | null;
  daily_orders_placed?: number;
  daily_remaining?: number | null;
  addon_groups?: AddonGroup[];
  variation_groups?: VariationGroup[];
  [key: string]: unknown;
}

/** Kitchen capacity block returned alongside GET /api/menu/items. */
export interface KitchenCapacity {
  daily_order_capacity: number | null;
  orders_today: number;
  is_at_capacity: boolean;
  [key: string]: unknown;
}

/** GET /api/menu/items response. */
export interface MenuItemsResponse {
  items: MenuItem[];
  kitchen?: KitchenCapacity | null;
}

/** GET /api/menu/items query parameters. */
export interface MenuItemsParams {
  category?: string;
  q?: string;
  available_only?: boolean;
  is_featured?: boolean;
  [key: string]: unknown;
}

/** GET /api/menu/items/:id/addons response (addon groups for one item). */
export interface ItemAddonsResponse {
  addon_groups?: AddonGroup[];
  groups?: AddonGroup[];
  addons?: MenuAddon[];
}

/** Admin create payload — POST /api/menu/items. */
export interface CreateMenuItemPayload {
  name: string;
  price: number;
  category_id?: Uuid | null;
  description?: string;
  image_url?: string;
  hp_earn_value?: number;
  hp_multiplier?: number;
  is_available?: boolean;
  is_featured?: boolean;
  is_secret?: boolean;
  daily_order_capacity?: number | null;
  [key: string]: unknown;
}

/** Admin update payload — PATCH /api/menu/items/:id (partial). */
export type UpdateMenuItemPayload = Partial<CreateMenuItemPayload>;

/** POST /api/menu/items/:id/image + POST /api/menu/addons/:id/image. */
export interface MenuImagePayload {
  image_url: string;
}

/** PATCH /api/menu/items/:id/availability + /items/bulk-availability. */
export interface AvailabilityPayload {
  is_available?: boolean;
  item_ids?: Uuid[];
  [key: string]: unknown;
}

/** PATCH /api/menu/kitchen-capacity. */
export interface KitchenCapacityPayload {
  daily_order_capacity: number | null;
}

/** POST/PATCH /api/menu/categories. */
export interface CategoryPayload {
  name: string;
  slug?: string;
  description?: string;
  image_url?: string;
  is_active?: boolean;
  display_order?: number;
}

/** POST /api/menu/addons + PATCH /api/menu/addons/:id. */
export interface AddonPayload {
  name: string;
  price: number;
  is_available?: boolean;
}

/** POST /api/menu/items/:id/addon-groups + PATCH .../:group_id. */
export interface AddonGroupPayload {
  name: string;
  min_select?: number;
  max_select?: number;
  options?: Array<{ name: string; price_delta: number }>;
}

/** POST /api/menu/items/:id/variation-groups (+ options). */
export interface VariationGroupPayload {
  name: string;
  min_select?: number;
  max_select?: number;
  options?: Array<{ name: string; price_delta: number }>;
}
