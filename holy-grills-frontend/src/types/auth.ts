/**
 * Auth, profile and address contract — /api/auth/*, /api/users/search (auth.py).
 * Verified against API_FIELD_REFERENCE.md §Auth and app/routes/auth.py.
 */
import type { IsoDate, MutationResult, Uuid } from './common';

/** Role enum — profiles.role (API_FIELD_REFERENCE.md Enum Master List). */
export type UserRole = 'student' | 'admin' | 'kitchen' | 'rider' | 'super_admin';

/** HP tier subtitle embedded in /auth/me. */
export interface TierSummary {
  id?: Uuid;
  name: string;
  slug?: string;
  multiplier?: number;
}

/** Wallet slice embedded in /auth/me. */
export interface WalletSummary {
  balance: number;
  virtual_account?: VirtualAccount | null;
}

/** Paystack virtual account (wallet.py / auth.py). */
export interface VirtualAccount {
  account_number?: string;
  bank_name?: string;
  account_name?: string;
  [key: string]: unknown;
}

/** GET /api/auth/me (also the `user` object returned by register/login). */
export interface AuthUser {
  id: Uuid;
  email: string;
  full_name: string;
  phone?: string | null;
  role: UserRole;
  date_of_birth?: IsoDate | null;
  hp_balance?: { active: number; pending: number };
  tier?: TierSummary | null;
  wallet?: WalletSummary | null;
  referral_code?: string | null;
  campus_id?: Uuid | null;
  avatar_url?: string | null;
  is_active?: boolean;
  push_enabled?: boolean;
  email_notifications?: boolean;
  [key: string]: unknown;
}

/** POST /api/auth/register + POST /api/auth/login response. */
export interface AuthSession {
  user: AuthUser;
  access_token: string;
  refresh_token: string;
}

/** POST /api/auth/register request body. */
export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
  phone?: string;
  date_of_birth?: IsoDate;
  referred_by_code?: string;
}

/** POST /api/auth/login request body. */
export interface LoginPayload {
  email: string;
  password: string;
}

/** POST /api/auth/refresh request/response (the access token may be rotated). */
export interface RefreshPayload {
  refresh_token: string;
  access_token?: string;
}

export interface RefreshResult {
  access_token: string;
  refresh_token?: string;
  rotated?: boolean;
}

/** PATCH /api/auth/profile request body — all fields optional. */
export interface UpdateProfilePayload {
  full_name?: string;
  phone?: string;
  date_of_birth?: IsoDate;
  push_enabled?: boolean;
  email_notifications?: boolean;
}

/** POST /api/auth/profile/photo — dedicated avatar endpoint. */
export interface UpdateProfilePhotoPayload {
  photo_url: string;
}

/** POST /api/auth/change-password request body. */
export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
}

/** POST /api/auth/reset-password (request) + /reset-password/confirm (set). */
export interface ResetPasswordPayload {
  email: string;
}

export interface ConfirmResetPayload {
  token: string;
  new_password: string;
}

/** POST /api/auth/verify-email request body. */
export interface VerifyEmailPayload {
  token: string;
}

/** POST /api/auth/device-token — push registration. */
export interface DeviceTokenPayload {
  token: string;
  platform: 'ios' | 'android' | 'web';
  device_model?: string;
}

/** POST /api/auth/logout, /logout-all-devices, DELETE /auth/account. */
export interface DeleteAccountPayload {
  password?: string;
  reason?: string;
}

/** Saved delivery address (GET/POST /api/auth/addresses). */
export interface Address {
  id: Uuid;
  label: string;
  address_line: string;
  city: string;
  state?: string | null;
  landmark?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  is_default?: boolean;
  [key: string]: unknown;
}

export interface CreateAddressPayload {
  label: string;
  address_line: string;
  city: string;
  state?: string;
  landmark?: string;
  latitude?: number;
  longitude?: number;
  is_default?: boolean;
}

export type UpdateAddressPayload = Partial<CreateAddressPayload>;

/** GET /api/auth/streak — weekly check-in progress. */
export interface StreakDay {
  day?: string;
  date?: IsoDate;
  status?: string;
  checked_in?: boolean;
  [key: string]: unknown;
}

export interface Streak {
  current_streak: number;
  longest_streak?: number;
  last_checkin_date?: IsoDate | null;
  week_progress?: StreakDay[];
  [key: string]: unknown;
}

/** GET /api/users/search (and the /api/auth/users/search alias). */
export interface UserSearchResult {
  id: Uuid;
  full_name: string;
  email?: string;
  avatar_url?: string | null;
  [key: string]: unknown;
}

export interface UserSearchParams {
  q?: string;
  query?: string;
  limit?: number;
  [key: string]: unknown;
}

export type AuthMutation = MutationResult;
