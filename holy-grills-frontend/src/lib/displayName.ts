/**
 * The name to call someone by — in copy, and in the admin pickers that address
 * a person.
 *
 * Mirrors the backend rule exactly (`app/services/squad_service.py` →
 * `resolve_display_name`): **nickname → full_name → email prefix → fallback**.
 * The backend data is the source of truth here: a student who set a nickname is
 * addressed by it in every backend notification, so a frontend message or an
 * admin grant toast that shows `full_name` would address the same person by a
 * different name. The leaderboard / hall-of-fame deliberately use a different
 * rule (`resolve_leaderboard_name`) and it stays server-side.
 */

type Profileish = {
  nickname?: string | null;
  full_name?: string | null;
  email?: string | null;
  name?: string | null;
} | null | undefined;

const clean = (value?: string | null) => (typeof value === 'string' ? value.trim() : '');

/** nickname → full_name → email prefix → the given fallback. */
export function displayName(profile: Profileish, fallback = 'Guest'): string {
  if (!profile) return fallback;
  const nickname = clean(profile.nickname);
  if (nickname) return nickname;
  const full = clean(profile.full_name) || clean(profile.name);
  if (full) return full;
  const email = clean(profile.email);
  if (email) return email.split('@')[0];
  return fallback;
}

/** The avatar initial for whoever this is: `displayName(profile).charAt(0)`. */
export function displayInitial(profile: Profileish, fallback = '?'): string {
  return (displayName(profile, fallback).charAt(0) || fallback).toUpperCase();
}
