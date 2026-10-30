/**
 * Squad contract — /api/squads (squads.py).
 * A squad is a standing group that can share order plans and HP.
 */
import type { MutationResult, Uuid } from './common';

export interface SquadMember {
  id?: Uuid;
  user_id?: Uuid;
  email?: string;
  full_name?: string;
  role?: 'owner' | 'member' | string;
  joined_at?: string;
  [key: string]: unknown;
}

export interface Squad {
  id: Uuid;
  name: string;
  owner_id?: Uuid;
  invite_code?: string;
  is_private?: boolean;
  members?: SquadMember[];
  member_count?: number;
  created_at?: string;
  [key: string]: unknown;
}

/** POST /api/squads request body. */
export interface CreateSquadPayload {
  name: string;
  is_private?: boolean;
  /** Emails to invite at creation time (squads.py:33). */
  emails?: string[];
  [key: string]: unknown;
}

/** POST /api/squads/:id/members request body. */
export interface AddSquadMemberPayload {
  email?: string;
  user_id?: Uuid;
  [key: string]: unknown;
}

export interface SquadMutation extends MutationResult {
  squad?: Squad;
}
