/**
 * Challenges & badges contract — /api/challenges/* (challenges.py).
 *
 * NOTE: API_FIELD_REFERENCE.md calls this subsystem "retired", but the blueprint
 * is registered and the frontend calls it — the code is authoritative here.
 * `GET /api/challenges/<id>` does not exist server-side (Phase 0 audit §5 M11).
 */
import type { MutationResult, Uuid } from './common';

/** A challenge/milestone row. */
export interface Challenge {
  id: Uuid;
  title?: string;
  name?: string;
  description?: string | null;
  hp_reward?: number;
  hp_bonus?: number;
  target?: number;
  is_active?: boolean;
  progress?: number;
  completed?: boolean;
  badge_slug?: string | null;
  [key: string]: unknown;
}

/** GET /api/challenges/my — the same rows with per-user progress. */
export type MyChallenge = Challenge;

/**
 * A challenge row as the live endpoint returns it: the canonical `Challenge`
 * fields plus the legacy aliases the backend still emits. Rewards.tsx reads both
 * spellings (`hp_awarded ?? hp_award`, `progress ?? current_progress`), so they
 * are declared rather than cast at the call site.
 */
export interface MyChallengeRow extends Challenge {
  hp_awarded?: number;
  hp_award?: number;
  current_progress?: number;
  requirement?: string;
  target_count?: number;
  trigger_type?: string;
  trigger_value?: number;
  slug?: string;
  expires_at?: string;
}

/** An earned badge row inside GET /api/challenges/my. */
export interface EarnedBadge {
  title?: string;
  name?: string;
  /** The badge's emoji/mark; rendered as-is when present. */
  icon_won?: string;
  [key: string]: unknown;
}

/**
 * GET /api/challenges/my — milestone_service.get_user_milestones() returns this
 * envelope (not a list), and both consumers (Rewards, Streak) read it as one.
 */
export interface MyChallengesEnvelope {
  badges?: EarnedBadge[];
  challenges_available?: MyChallengeRow[];
  challenges_completed?: MyChallengeRow[];
  [key: string]: unknown;
}

/** PWA/push bonus status (GET /api/challenges/pwa-push-bonus-status). */
export interface PwaPushBonusStatus {
  pwa_installed?: boolean;
  push_subscribed?: boolean;
  bonus_granted?: boolean;
  hp_awarded?: number;
  [key: string]: unknown;
}

/** POST /api/challenges/social-follow request body. */
export interface SocialFollowPayload {
  platform?: 'instagram' | 'twitter' | 'tiktok' | 'facebook' | string;
  handle?: string;
  [key: string]: unknown;
}

/** Admin create/update payload — POST/PATCH /api/challenges/admin. */
export interface ChallengePayload {
  title: string;
  description?: string;
  hp_reward?: number;
  target?: number;
  is_active?: boolean;
}

/** POST /api/challenges/:id/complete. */
export interface CompleteChallengePayload {
  proof?: string;
  [key: string]: unknown;
}

export type ChallengeMutation = MutationResult;
