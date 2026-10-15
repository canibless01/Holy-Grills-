/**
 * Graduation claim contract — /api/graduation/claim (graduation.py).
 */
import type { MutationResult } from './common';

/** POST /api/graduation/claim request body. */
export interface GraduationClaimPayload {
  full_name?: string;
  matric_number?: string;
  graduation_year?: number | string;
  department?: string;
  [key: string]: unknown;
}

export interface GraduationClaimResult extends MutationResult {
  claim?: {
    id?: string;
    status?: 'pending' | 'approved' | 'rejected' | string;
    created_at?: string;
    [key: string]: unknown;
  };
  eligible?: boolean;
}
