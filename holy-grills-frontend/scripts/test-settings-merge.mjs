/**
 * settingsMerge tests — the "admin sees the number, users get another" guard.
 * ============================================================================
 * src/lib/settingsMerge.ts decides whether a privileged system_settings row is
 * allowed to override the value a normal user receives. Getting it wrong is
 * invisible in the admin panel and obvious on the live site: the floating
 * WhatsApp button opened a number that matched nothing in the settings table,
 * because GET /admin/settings returns every row for every campus (private rows
 * included) in arbitrary order and the old merge let the last one win.
 *
 * Exercised against the real module with esbuild, no test framework — the same
 * approach as test-value-text and test-safe-navigation.
 *
 *   npm run test:settings-merge
 */
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const out = join(root, 'node_modules', '.cache-settings-merge.mjs');
execFileSync(join(root, 'node_modules', '.bin', 'esbuild'), [
  join(root, 'src', 'lib', 'settingsMerge.ts'),
  '--loader:.ts=ts',
  '--format=esm',
  `--outfile=${out}`,
]);
// Must stay import-free: that is what keeps it testable here and safe to call
// from anywhere in the app.
writeFileSync(out, readFileSync(out, 'utf8').replace(/from "[^"]*"/g, () => { throw new Error('unexpected import'); }));

const { mergeAdminSettings } = await import(out);

let failures = 0;
const eq = (label, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures += 1;
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${ok ? '' : ` — got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`}`);
};

const globalRow = (key, value) => ({ key, value, campus_id: null });
const campusRow = (key, value, campus_id) => ({ key, value, campus_id });

console.log('mergeAdminSettings');

// ── the reported WhatsApp bug ────────────────────────────────────────────
eq(
  'a private admin row must not override the public value',
  mergeAdminSettings(
    { whatsapp_support_number: '2348011111111' },                 // what users get (is_public = true)
    [globalRow('whatsapp_support_number', '2348099999999')],      // a private/other row the admin can see
    null,
  ),
  { whatsapp_support_number: '2348011111111' },
);

eq(
  'a per-campus row must not override the global value for a visitor of another campus',
  mergeAdminSettings(
    { whatsapp_support_number: '2348011111111' },
    [campusRow('whatsapp_support_number', '2348022222222', 'futa'), globalRow('whatsapp_support_number', '2348033333333')],
    'lagos',
  ),
  { whatsapp_support_number: '2348011111111' },
);

// ── precedence when the public config did NOT resolve the key ─────────────
eq(
  'campus row beats global row regardless of array order (campus last)',
  mergeAdminSettings({}, [globalRow('k', 'global'), campusRow('k', 'campus', 'futa')], 'futa'),
  { k: 'campus' },
);

eq(
  'campus row beats global row regardless of array order (campus first)',
  mergeAdminSettings({}, [campusRow('k', 'campus', 'futa'), globalRow('k', 'global')], 'futa'),
  { k: 'campus' },
);

eq(
  'another campus row is ignored entirely',
  mergeAdminSettings({}, [campusRow('k', 'other', 'lagos')], 'futa'),
  {},
);

eq(
  'a global row still applies when the visitor has no campus',
  mergeAdminSettings({}, [globalRow('k', 'global'), campusRow('k', 'campus', 'futa')], null),
  { k: 'global' },
);

eq(
  'a campus row is still usable when the visitor has no campus selected',
  mergeAdminSettings({}, [campusRow('k', 'campus', 'futa')], null).k,
  undefined,
);

// ── null / shape safety ──────────────────────────────────────────────────
eq(
  'a null value never blanks out a resolved value',
  mergeAdminSettings({ k: 'good' }, [globalRow('k', null)], null),
  { k: 'good' },
);

eq(
  'a null value never becomes a key',
  mergeAdminSettings({}, [globalRow('k', null)], null),
  {},
);

eq('non-array input is a no-op', mergeAdminSettings({ a: 1 }, null, null), { a: 1 });
eq('object input is a no-op', mergeAdminSettings({ a: 1 }, { key: 'k', value: 'v' }, null), { a: 1 });
eq(
  'rows with no key are skipped',
  mergeAdminSettings({}, [{ value: 'v' }, null, undefined, { key: '', value: 'v' }], null),
  {},
);

// ── it must still EXTEND, not just protect ───────────────────────────────
eq(
  'private-only keys are still visible to an admin',
  mergeAdminSettings({ public_key: 'p' }, [globalRow('secret_key', 's')], null),
  { public_key: 'p', secret_key: 's' },
);

eq(
  'returns the same object it mutated',
  (() => { const t = {}; return mergeAdminSettings(t, [globalRow('k', 'v')], null) === t; })(),
  true,
);

console.log(failures === 0 ? '\n[settings-merge] ok\n' : `\n[settings-merge] FAIL — ${failures} assertion(s)\n`);
process.exit(failures === 0 ? 0 : 1);
