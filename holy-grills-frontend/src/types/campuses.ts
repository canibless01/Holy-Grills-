/**
 * Campus contract — /api/campuses (campuses.py). Public list used by the
 * campus gate and the admin campus selector.
 */
import type { Uuid } from './common';

export interface Campus {
  id: Uuid;
  name: string;
  slug?: string;
  lat?: number | null;
  lon?: number | null;
  is_active?: boolean;
  [key: string]: unknown;
}

/** GET /api/campuses → { campuses, count }. */
export interface CampusesResponse {
  campuses: Campus[];
  count?: number;
}
