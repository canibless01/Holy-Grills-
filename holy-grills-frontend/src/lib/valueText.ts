/**
 * Coercing backend values into text the UI can safely render.
 * ============================================================================
 * Supabase happily returns a nested object where the frontend expects a label
 * (a joined row, a tier, a status). Rendering one of those as a React child
 * throws "Objects are not valid as a React child (found: object with keys …)",
 * and because the throw happens during render it takes the whole panel — or
 * the whole admin section — down with it.
 *
 * That is exactly what the User Management drawer did: the HP endpoint nests
 * the tier row twice, so a "tier" pill rendered a container and the drawer
 * crashed on open.
 *
 * These helpers are import-free on purpose so they can be unit-tested with
 * esbuild alone (`npm run test:value-text`) and used from anywhere.
 */

/** Maximum nesting we are willing to walk before giving up. */
const MAX_DEPTH = 4;

/** Keys that commonly carry the human-readable label on a joined row. */
const LABEL_KEYS = ['name', 'tier_name', 'label', 'title', 'full_name', 'code', 'value'] as const;

/**
 * Display name for a tier, from any of the shapes the backend uses.
 *
 * get_user_tier()  → { tier: <hp_tiers row>, is_in_grace_period: … }
 * get_hp_balance() → { …, tier: { tier: <hp_tiers row>, … } }
 * /admin/users/:id → { …, tier: { tier: <row>, … } }
 *
 * Always returns a string or null — never the container — so a component can
 * render it without a second thought.
 */
export function hpTierName(info: unknown, depth = 0): string | null {
  if (!info || depth > MAX_DEPTH) return null;
  if (typeof info === 'string') {
    const trimmed = info.trim();
    return trimmed || null;
  }
  if (typeof info === 'number') return String(info);
  if (typeof info !== 'object' || Array.isArray(info)) return null;

  const row = info as Record<string, unknown>;
  for (const key of LABEL_KEYS) {
    const value = row[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
    if (typeof value === 'number') return String(value);
  }
  // Not a label at this level — the row is a container, so step into it.
  return hpTierName(row.tier ?? row.hp_tier ?? row.tier_info, depth + 1);
}

/**
 * Any backend value as display text. Objects are reduced to a label rather
 * than handed to React. Use for every "this should be a word" read.
 */
export function safeText(value: unknown, fallback = ''): string {
  if (value == null) return fallback;
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (typeof value === 'object') {
    const label = hpTierName(value);
    return label ?? fallback;
  }
  return fallback;
}

/**
 * WhatsApp number in the digits-only international form wa.me expects.
 * " +234 801-234 5678 " → "2348012345678"; "08012345678" → "2348012345678".
 *
 * Guards the click-to-chat link: a NaN here produced https://wa.me/NaN and
 * looked exactly like "the button isn't reading my setting".
 */
export function normalizeWhatsAppNumber(raw: unknown): string {
  const digits = String(raw ?? '').replace(/\D/g, '');
  if (!digits) return '';
  // A leading 0 is a local trunk prefix; wa.me needs the country code.
  return digits.startsWith('0') ? `234${digits.slice(1)}` : digits;
}
