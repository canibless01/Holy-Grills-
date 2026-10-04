/**
 * Barrel for the shared Holy Grills API contract types.
 *
 * One module per backend domain (mirrors the Flask blueprint files), plus
 * `common` for the envelopes/error shapes every endpoint shares.
 * These are types only — importing this file adds no runtime code.
 */
export * from './common';
export * from './auth';
export * from './config';
export * from './uploads';
export * from './menu';
export * from './cart';
export * from './orders';
export * from './order-locks';
export * from './saved';
export * from './squads';
export * from './hp';
export * from './wallet';
export * from './rewards';
export * from './free-sides';
export * from './exclusive-spin';
export * from './marketplace';
export * from './events';
export * from './referrals';
export * from './notifications';
export * from './leaderboard';
export * from './challenges';
export * from './graduation';
export * from './kitchen';
export * from './riders';
export * from './storefront';
export * from './analytics';
export * from './economics';
export * from './delivery';
export * from './admin';
export * from './campuses';
export * from './departments';
export * from './academic-levels';
export * from './academic-calendar';
