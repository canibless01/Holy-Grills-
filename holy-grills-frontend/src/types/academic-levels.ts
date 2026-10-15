/**
 * Academic levels — /api/academic-levels (public) and /api/admin/academic-levels
 * (academic_levels.py).
 */
import type { Uuid } from './common';

export interface AcademicLevel {
  id: Uuid;
  name: string;
  code?: string | null;
  display_order?: number;
  is_active?: boolean;
  [key: string]: unknown;
}

/** GET /api/academic-levels → { levels, count }. */
export interface AcademicLevelsResponse {
  levels: AcademicLevel[];
  count?: number;
}

export interface AcademicLevelPayload {
  name: string;
  code?: string;
  display_order?: number;
  is_active?: boolean;
}
