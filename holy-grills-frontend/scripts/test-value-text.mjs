/**
 * valueText tests — the "don't crash the panel" guards.
 * ============================================================================
 * src/lib/valueText.ts is what stands between a nested Supabase payload and
 * React's renderer. Rendering an object as a React child throws during render,
 * which takes down the whole admin section — that is how the User Management
 * drawer died (the HP endpoint nests the tier row twice).
 *
 * Exercised against the real module the same way test-safe-navigation does it:
 * esbuild transpiles it, no test framework is added for one file.
 *
 *   npm run test:value-text
 */
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const out = join(root, 'node_modules', '.cache-value-text.mjs');
execFileSync(join(root, 'node_modules', '.bin', 'esbuild'), [
  join(root, 'src', 'lib', 'valueText.ts'),
  '--loader:.ts=ts',
  '--format=esm',
  `--outfile=${out}`,
]);
// The module must stay import-free: that is what keeps it testable here and
// safe to call from anywhere.
writeFileSync(out, readFileSync(out, 'utf8').replace(/from "[^"]*"/g, () => { throw new Error('unexpected import'); }));

const { hpTierName, safeText, normalizeWhatsAppNumber } = await import(out);

let failures = 0;
const eq = (label, got, want) => {
  const ok = got === want;
  if (!ok) failures += 1;
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${ok ? '' : ` — got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`}`);
};

// The row shape get_user_tier() returns.
const TIER_ROW = { id: 't-1', name: 'Flame', min_points: 500, earn_multiplier: 1.08 };
// …wrapped by get_user_tier() itself.
const TIER_INFO = { tier: TIER_ROW, is_in_grace_period: false, grace_period_ends_at: null };
// …and that, embedded in get_hp_balance()'s dict under its own `tier` key.
const HP_BALANCE = { active: 120, pending: 30, total_visible: 150, tier: TIER_INFO, degraded: false };

console.log('hpTierName');
eq('plain string', hpTierName('Blaze'), 'Blaze');
eq('tier row', hpTierName(TIER_ROW), 'Flame');
eq('tier container (get_user_tier)', hpTierName(TIER_INFO), 'Flame');
eq('twice-nested (hp_balance.tier)', hpTierName(HP_BALANCE.tier), 'Flame');
eq('the crash shape is a string, not an object', typeof hpTierName(HP_BALANCE.tier), 'string');
eq('null', hpTierName(null), null);
eq('undefined', hpTierName(undefined), null);
eq('empty string', hpTierName('   '), null);
eq('object with no label key', hpTierName({ id: 1, min_points: 10 }), null);
eq('array is refused', hpTierName([TIER_ROW]), null);
eq('self-referential payload terminates', hpTierName((() => { const a = {}; a.tier = a; return a; })()), null);
eq('number', hpTierName(3), '3');

console.log('\nsafeText');
eq('string passthrough', safeText('Delivered'), 'Delivered');
eq('number', safeText(42), '42');
eq('boolean', safeText(false), 'false');
eq('null falls back', safeText(null, '—'), '—');
eq('nested row -> label', safeText(TIER_INFO, '—'), 'Flame');
eq('unlabelled object falls back', safeText({ id: 1 }, '—'), '—');
eq('array falls back', safeText([1, 2], '—'), '—');

console.log('\nnormalizeWhatsAppNumber');
eq('already international', normalizeWhatsAppNumber('2348012345678'), '2348012345678');
eq('formatted with + and spaces', normalizeWhatsAppNumber('+234 801 234 5678'), '2348012345678');
eq('dashes', normalizeWhatsAppNumber('0801-234-5678'), '2348012345678');
eq('local trunk prefix', normalizeWhatsAppNumber('08012345678'), '2348012345678');
eq('empty -> empty (no wa.me/NaN)', normalizeWhatsAppNumber(''), '');
eq('null -> empty', normalizeWhatsAppNumber(null), '');
eq('non-numeric text -> empty', normalizeWhatsAppNumber('call me'), '');
eq('undefined -> empty', normalizeWhatsAppNumber(undefined), '');

// Regression: the exact value the floating button used to build a link from.
const stored = '+234 801 234 5678';
eq('button href is never wa.me/NaN', `https://wa.me/${normalizeWhatsAppNumber(stored)}`, 'https://wa.me/2348012345678');

rmSync(out, { force: true });
console.log(failures === 0 ? '\nHELPER: all assertions pass' : `\nHELPER: ${failures} FAILURES`);
process.exit(failures === 0 ? 0 : 1);
