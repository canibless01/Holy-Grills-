/**
 * canonicalOrigin tests — the served origin must match the OneSignal origin.
 * ============================================================================
 * The OneSignal web app is configured for exactly one origin
 * (https://holygrills.online). Browsers treat the www alias as a different
 * origin, so the push SDK cannot initialize there. `src/lib/canonicalOrigin.ts`
 * normalises the alias onto the configured origin without losing anything in
 * the URL (path, query string, hash) and leaves every other host alone.
 *
 *   npm run test:canonical-origin
 */
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const out = join(root, 'node_modules', `.cache-canonical-origin-${process.pid}.mjs`);

execFileSync(join(root, 'node_modules', '.bin', 'esbuild'), [
  join(root, 'src', 'lib', 'canonicalOrigin.ts'),
  '--loader:.ts=ts',
  '--format=esm',
  `--outfile=${out}`,
]);

// The module must be dependency-free: a stray import here would mean the
// guarantee can drift with something else's build.
const bundled = readFileSync(out, 'utf8');
if (/^\s*import\s/m.test(bundled)) {
  console.error('  FAIL canonicalOrigin.ts must not import anything');
  process.exit(1);
}

const {
  CANONICAL_HOST, CANONICAL_ORIGIN, WWW_ALIAS_HOST,
  isWwwAliasHost, canonicalRedirectTarget,
} = await import(`${out}?v=${Date.now()}`);

let failures = 0;
const eq = (label, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures += 1;
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${ok ? '' : ` — got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`}`);
};

const at = (hostname, pathname = '/', search = '', hash = '') => ({ protocol: 'https:', hostname, pathname, search, hash });

eq('canonical host is the apex domain', CANONICAL_HOST, 'holygrills.online');
eq('canonical origin is https on the apex', CANONICAL_ORIGIN, 'https://holygrills.online');
eq('www alias host', WWW_ALIAS_HOST, 'www.holygrills.online');

eq('www alias is recognised', isWwwAliasHost('www.holygrills.online'), true);
eq('alias match is case-insensitive', isWwwAliasHost('WWW.HolyGrills.Online'), true);
eq('apex is not an alias', isWwwAliasHost('holygrills.online'), false);
eq('a lookalike domain is not an alias', isWwwAliasHost('www.holygrills.online.evil.test'), false);
eq('localhost is never redirected', canonicalRedirectTarget(at('localhost')), null);
eq('vercel preview host is never redirected', canonicalRedirectTarget(at('holy-grills-git-main.vercel.app')), null);

// The redirect target is the whole point: same page, canonical origin.
eq('www root -> apex root', canonicalRedirectTarget(at('www.holygrills.online')), 'https://holygrills.online/');
eq(
  'path is preserved',
  canonicalRedirectTarget(at('www.holygrills.online', '/orders/abc')),
  'https://holygrills.online/orders/abc',
);
eq(
  'payment-return query string is preserved',
  canonicalRedirectTarget(at('www.holygrills.online', '/order-confirmation/42', '?payment_return=1')),
  'https://holygrills.online/order-confirmation/42?payment_return=1',
);
eq(
  'referral query string is preserved',
  canonicalRedirectTarget(at('www.holygrills.online', '/referrals', '?ref=user-1')),
  'https://holygrills.online/referrals?ref=user-1',
);
eq(
  'hash is preserved',
  canonicalRedirectTarget(at('www.holygrills.online', '/menu', '?campus=futa', '#top')),
  'https://holygrills.online/menu?campus=futa#top',
);
eq(
  'http on the alias still lands on https at the apex',
  canonicalRedirectTarget({ protocol: 'http:', hostname: 'www.holygrills.online', pathname: '/menu' }),
  'https://holygrills.online/menu',
);
eq(
  'empty path normalises to root',
  canonicalRedirectTarget({ hostname: 'www.holygrills.online', pathname: '' }),
  'https://holygrills.online/',
);
eq('missing location is a no-op', canonicalRedirectTarget(null), null);
eq('apex is already canonical', canonicalRedirectTarget(at('holygrills.online', '/menu')), null);

console.log(failures === 0
  ? 'PASS canonical origin: www alias normalises to https://holygrills.online with path/query/hash intact; every other host untouched'
  : `${failures} canonical-origin check(s) failed`);
if (failures) process.exit(1);
