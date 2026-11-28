/**
 * Public configuration contract.
 *
 * Public settings are served by `GET /api/storefront/config/public` as a flat
 * key→value map (see `PublicConfig` in ./storefront) — `lib/featureConfig.ts`
 * reads them from there. The old `GET /settings` call 404'd and was removed
 * (docs/WIRING_AUDIT.md §3.2).
 */
import type { PublicConfig } from './storefront';

/** Response of GET /api/admin/settings (admin scope only). */
export interface SettingsListResponse {
  settings: Array<{ key: string; value: unknown; [k: string]: unknown }>;
  count?: number;
}

/** The public key/value map the student app can read unauthenticated. */
export type PublicSettings = PublicConfig & {
  /** Streak / free-side / reward values live here too (any public system_setting key). */
  [key: string]: unknown;
};
