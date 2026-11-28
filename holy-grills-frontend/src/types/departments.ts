/**
 * Departments & faculties — /api/departments (public) and
 * /api/admin/departments (departments.py).
 */
import type { Uuid } from './common';

export interface Faculty {
  name: string;
  [key: string]: unknown;
}

export interface Department {
  id: Uuid;
  name: string;
  faculty?: string | null;
  code?: string | null;
  is_active?: boolean;
  [key: string]: unknown;
}

/** GET /api/departments → { departments, count }. */
export interface DepartmentsResponse {
  departments: Department[];
  count?: number;
}

/** GET /api/departments/faculties → { faculties }. */
export interface FacultiesResponse {
  faculties: Faculty[] | string[];
  count?: number;
}

export interface DepartmentPayload {
  name: string;
  faculty?: string;
  code?: string;
  is_active?: boolean;
}
