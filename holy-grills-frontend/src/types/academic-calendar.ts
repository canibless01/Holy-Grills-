/**
 * Academic calendar — /api/academic-calendar/current (public) and
 * /api/admin/academic-calendar (academic_calendar.py).
 * Periods drive analytics comparisons (exam vs normal days) and promos.
 */
import type { IsoDate, MutationResult, Uuid } from './common';

export interface AcademicCalendarEntry {
  id: Uuid;
  name?: string;
  period_type?: string;
  start_date?: IsoDate;
  end_date?: IsoDate;
  campus_id?: Uuid | null;
  is_active?: boolean;
  [key: string]: unknown;
}

/** GET /api/academic-calendar/current → { current_period } or { message }. */
export interface CurrentAcademicPeriodResponse {
  current_period: AcademicCalendarEntry | null;
  message?: string;
}

/** GET /api/admin/academic-calendar → { academic_calendar, count }. */
export interface AcademicCalendarResponse {
  academic_calendar: AcademicCalendarEntry[];
  count?: number;
}

export interface AcademicCalendarPayload {
  name: string;
  period_type?: string;
  start_date: IsoDate;
  end_date: IsoDate;
  campus_id?: Uuid | null;
  [key: string]: unknown;
}

export type AcademicCalendarMutation = MutationResult;
