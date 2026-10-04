/**
 * Shared API primitives — Holy Grills backend contract.
 *
 * Source of truth for the response/error envelope every endpoint uses:
 *   - success: a JSON object (domain payload); list endpoints wrap arrays in a
 *     keyed object, e.g. { orders: [...] }, which `liveApi` unwraps.
 *   - error:   { "error": "<human readable message>" } with a non-2xx status
 *              (Flask `abort(...)`/`jsonify({"error": ...})` — see app/messages.py).
 *
 * Nothing in this folder is runtime code; it is types only.
 */

/** UUID string (Postgres uuid / PostgREST id). */
export type Uuid = string;

/** ISO-8601 timestamp string as returned by PostgREST. */
export type IsoDateTime = string;

/** Calendar date, `YYYY-MM-DD`. */
export type IsoDate = string;

/** Clock time, `HH:MM`. */
export type ClockTime = string;

/** Naira amount (numeric). */
export type Naira = number;

/** Holy Points (integer). */
export type Hp = number;

/**
 * Error body returned by every failing request.
 * `apiClient` raises `ApiError(status, data.error ?? data.message, data)`.
 */
export interface ApiErrorBody {
  error?: string;
  message?: string;
  detail?: string;
}

/** A list endpoint that wraps its array in a keyed object, e.g. { orders: [] }. */
export type ListEnvelope<K extends string, T> = { [P in K]: T[] } & {
  count?: number;
};

/** Any list endpoint's possible shapes — a bare array or a keyed envelope. */
export type ListResponse<T, K extends string = string> =
  | T[]
  | ListEnvelope<K, T>
  | Record<string, unknown>;

/** Success envelope used by mutation endpoints that only report a message. */
export interface MutationResult {
  message?: string;
  success?: boolean;
  count?: number;
  [key: string]: unknown;
}

/** Mutation that returns the created/updated record under a key, e.g. { lock: {...} }. */
export type RecordEnvelope<K extends string, T> = { [P in K]: T } & MutationResult;

/** Standard paginated query parameters accepted by the list endpoints. */
export interface PaginationParams {
  page?: number;
  per_page?: number;
}

/** Every authenticated request sends `Authorization: Bearer <access_token>`; the
 *  optional `X-Campus-ID` header scopes campus-aware reads (see apiClient.js). */
export interface AuthHeaders {
  Authorization?: string;
  'X-Campus-ID'?: string;
}

/** GET /api/health — public connectivity probe (health.py). */
export interface HealthStatus {
  status: 'ok' | 'degraded';
  api: string;
  version: string;
  checks: {
    supabase: string;
    supabase_auth: string;
    redis: string;
  };
}

/** A raw-text endpoint (GET /api/analytics/export) returns CSV/plain text. */
export type RawTextResponse = string;
