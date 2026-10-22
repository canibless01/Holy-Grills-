/**
 * Saved-for-later contract — /api/saved (saved_for_later.py).
 */
import type { Naira, Uuid } from './common';
import type { MenuItem } from './menu';

export interface SavedItem {
  id: Uuid;
  menu_item_id?: Uuid;
  quantity?: number;
  unit_price?: Naira;
  menu_item?: MenuItem | null;
  name_snapshot?: string;
  created_at?: string;
  [key: string]: unknown;
}

/** GET /api/saved → { items, count }. */
export interface SavedItemsResponse {
  items: SavedItem[];
  count?: number;
}

/** POST /api/saved request body. */
export interface SaveItemPayload {
  menu_item_id: Uuid;
  quantity?: number;
}

/** PATCH /api/saved/:id request body. */
export interface UpdateSavedItemPayload {
  quantity?: number;
}
