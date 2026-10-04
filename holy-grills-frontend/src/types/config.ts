/**
 * Public configuration contract.
 *
 * `liveApi.config.getPublic()` calls `GET /settings` — that path does **not**
 * exist on the backend (Phase 0 audit §5 M12). Public settings are served by
 * `GET /api/storefront/config/public` (see `PublicConfig` in ./storefront).
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
