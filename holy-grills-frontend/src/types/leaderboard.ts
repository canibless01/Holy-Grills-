/**
 * Leaderboard contract — /api/leaderboard/* (leaderboard.py).
 */
import type { IsoDateTime, Uuid } from './common';

/** leaderboard period filter. */
export type LeaderboardPeriod = 'weekly' | 'monthly' | 'all_time';

/** One ranking row. */
export interface LeaderboardEntry {
  rank: number;
  user_id?: Uuid;
  full_name?: string;
  hp_total?: number;
  hp?: number;
  tier_name?: string | null;
  avatar_url?: string | null;
  is_me?: boolean;
  [key: string]: unknown;
}

/** GET /api/leaderboard. */
export interface LeaderboardResponse {
  period_key?: string;
  period_type?: LeaderboardPeriod;
  rankings: LeaderboardEntry[];
}

export interface LeaderboardParams {
  period?: LeaderboardPeriod;
  limit?: number;
  [key: string]: unknown;
}

/** GET /api/leaderboard/my-rank (bare array of per-period ranks). */
export interface MyRank {
  period_type?: LeaderboardPeriod;
  rank?: number | null;
  hp_total?: number;
  [key: string]: unknown;
}

/** GET /api/leaderboard/squad. */
export interface SquadLeaderboardEntry extends LeaderboardEntry {
  squad_id?: Uuid;
  squad_name?: string;
}

/** GET /api/leaderboard/hall-of-fame. */
export interface HallOfFameEntry {
  id?: Uuid;
  period_key?: string;
  period_type?: string;
  user_id?: Uuid;
  full_name?: string;
  hp_total?: number;
  snapshot_at?: IsoDateTime;
  [key: string]: unknown;
}

/** GET /api/leaderboard/hall-of-fame/inductees. */
export interface HallOfFameInductee {
  id: Uuid;
  user_id?: Uuid;
  full_name?: string;
  period_key?: string;
  hp_total?: number;
  tier_name?: string | null;
  reward_status?: string | null;
  [key: string]: unknown;
}
