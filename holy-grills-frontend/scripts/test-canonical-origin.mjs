/**
 * canonicalOrigin tests — the served origin must match the OneSignal origin.
 * ============================================================================
 * The OneSignal web app is configured for exactly one origin
 * (https://holygrills.online). Browsers treat the www alias as a different
 * origin, so the push SDK cannot initialize there. `src/lib/canonicalOrigin.ts`
 * normalises the alias onto the configured origin without losing anything in
 * the URL (path, query string, hash) and leaves every other host alone.
 *
 * The second half of this suite is the important one for the 29 Oct incident:
 * a client-side origin redirect must never be able to ping-pong with a host
 * redirect. One attempt per document, none while a bounce is in progress, and
 * the marker is stripped afterwards.
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

let failures = 0;
const eq = (label, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures += 1;
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${ok ? '' : ` — got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`}`);
};

const at = (hostname, pathname = '/', search = '', hash = '') => ({ protocol: 'https:', hostname, pathname, search, hash });

// Fresh module instance = a fresh page load. Each load gets its own in-module
// "redirect already started" state, which is exactly what we want to test.
let load = 0;
const freshModule = async () => {
  load += 1;
  return import(`${out}?load=${load}-${Date.now()}`);
};

/** A minimal `window` with a counting redirect. */
const installWindow = (mod, location) => {
  const calls = [];
  globalThis.window = { location: { ...location, replace: (url) => { calls.push(url); } }, history: null };
  return calls;
};

// ── 1. Pure URL contract ────────────────────────────────────────────────────
{
  const { CANONICAL_HOST, CANONICAL_ORIGIN, WWW_ALIAS_HOST, BOUNCE_PARAM, isWwwAliasHost, canonicalRedirectTarget, hasBounceMarker } =
    await freshModule();

  eq('canonical host is the apex domain', CANONICAL_HOST, 'holygrills.online');
  eq('canonical origin is https on the apex', CANONICAL_ORIGIN, 'https://holygrills.online');
  eq('www alias host', WWW_ALIAS_HOST, 'www.holygrills.online');
  eq('bounce marker param', BOUNCE_PARAM, 'hg_origin');

  eq('www alias is recognised', isWwwAliasHost('www.holygrills.online'), true);
  eq('alias match is case-insensitive', isWwwAliasHost('WWW.HolyGrills.Online'), true);
  eq('apex is not an alias', isWwwAliasHost('holygrills.online'), false);
  eq('a lookalike domain is not an alias', isWwwAliasHost('www.holygrills.online.evil.test'), false);

  eq('marker is detected', hasBounceMarker('?hg_origin=bounced'), true);
  eq('marker detection ignores other params', hasBounceMarker('?utm=1&hg_origin=bounced'), true);
  eq('no marker in a plain query', hasBounceMarker('?utm=1'), false);
  eq('empty search has no marker', hasBounceMarker(''), false);

  eq('localhost is never redirected', canonicalRedirectTarget(at('localhost')), null);
  eq('vercel preview host is never redirected', canonicalRedirectTarget(at('holy-grills-git-main.vercel.app')), null);

  // The redirect target is the whole point: same page, canonical origin, plus
  // our marker so a host bounce back is provable.
  eq('www root -> apex root', canonicalRedirectTarget(at('www.holygrills.online')), `https://holygrills.online/?${BOUNCE_PARAM}=bounced`);
  eq(
    'path is preserved',
    canonicalRedirectTarget(at('www.holygrills.online', '/orders/abc')),
    `https://holygrills.online/orders/abc?${BOUNCE_PARAM}=bounced`,
  );
  eq(
    'payment-return query string is preserved',
    canonicalRedirectTarget(at('www.holygrills.online', '/order-confirmation/42', '?payment_return=1')),
    `https://holygrills.online/order-confirmation/42?payment_return=1&${BOUNCE_PARAM}=bounced`,
  );
  eq(
    'referral query string is preserved',
    canonicalRedirectTarget(at('www.holygrills.online', '/referrals', '?ref=user-1')),
    `https://holygrills.online/referrals?ref=user-1&${BOUNCE_PARAM}=bounced`,
  );
  eq(
    'hash is preserved',
    canonicalRedirectTarget(at('www.holygrills.online', '/menu', '?campus=futa', '#top')),
    `https://holygrills.online/menu?campus=futa&${BOUNCE_PARAM}=bounced#top`,
  );
  eq(
    'http on the alias also lands on https at the apex',
    canonicalRedirectTarget({ protocol: 'http:', hostname: 'www.holygrills.online', pathname: '/menu' }),
    `https://holygrills.online/menu?${BOUNCE_PARAM}=bounced`,
  );
  eq(
    'empty path normalises to root',
    canonicalRedirectTarget({ hostname: 'www.holygrills.online', pathname: '' }),
    `https://holygrills.online/?${BOUNCE_PARAM}=bounced`,
  );
  eq('missing location is a no-op', canonicalRedirectTarget(null), null);
  eq('apex is already canonical', canonicalRedirectTarget(at('holygrills.online', '/menu')), null);

  // ── 2. Bounce protection (the infinite-reload guard) ──────────────────────
  eq(
    'a URL already carrying the marker is never redirected again',
    canonicalRedirectTarget(at('www.holygrills.online', '/menu', '?hg_origin=bounced')),
    null,
  );
  eq(
    'an explicitly bounced document is not redirected',
    canonicalRedirectTarget(at('www.holygrills.online', '/menu'), { bounced: true }),
    null,
  );
}

// ── 3. Runtime behaviour: one attempt, then stand down ──────────────────────
{
  const mod = await freshModule();
  globalThis.sessionStorage = undefined;
  let calls = installWindow(mod, at('www.holygrills.online', '/menu', '?campus=futa'));
  eq('first load on the alias redirects', mod.enforceCanonicalOrigin(), true);
  eq('redirect target carries the marker', calls, [`https://holygrills.online/menu?campus=futa&hg_origin=bounced`]);
  eq('a second call in the same document does not navigate again', mod.enforceCanonicalOrigin(), true);
  eq('still exactly one navigation', calls.length, 1);
}

{
  // The host bounced us back (marker survived the redirect) → render, no reload.
  const mod = await freshModule();
  globalThis.sessionStorage = undefined;
  const calls = installWindow(mod, at('www.holygrills.online', '/menu', '?hg_origin=bounced'));
  eq('bounced document does not redirect', mod.enforceCanonicalOrigin(), false);
  eq('bounced document starts no navigation', calls, []);
  eq('bounce is reported to the caller', mod.isBeingOriginBounced(), true);
  eq('the alias is still recognised as a non-push origin', mod.isOnAliasedOrigin(), true);
}

{
  // Storage-backed memory: even if the host drops the query marker, a return to
  // the alias inside the window counts as a bounce.
  const mod = await freshModule();
  const store = new Map();
  globalThis.sessionStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  };
  const first = installWindow(mod, at('www.holygrills.online', '/menu'));
  eq('first load redirects', mod.enforceCanonicalOrigin(), true);
  eq('attempt was recorded', [...store.keys()], ['hg_canonical_origin_attempt_at']);

  const back = await freshModule(); // new document, host dropped ?hg_origin
  const calls = installWindow(back, at('www.holygrills.online', '/menu'));
  eq('a quick return to the alias is treated as a bounce', back.enforceCanonicalOrigin(), false);
  eq('no second navigation', calls, []);

  const later = await freshModule();
  store.set('hg_canonical_origin_attempt_at', String(Date.now() - mod.BOUNCE_WINDOW_MS - 1000));
  installWindow(later, at('www.holygrills.online', '/menu'));
  eq('after the window expires the alias may redirect again', later.enforceCanonicalOrigin(), true);
}

// ── 4. Marker cleanup never navigates and keeps real params ─────────────────
{
  const mod = await freshModule();
  const replaced = [];
  globalThis.window = {
    location: at('holygrills.online', '/menu', '?campus=futa&hg_origin=bounced', '#top'),
    history: { state: { keep: true }, replaceState: (state, _title, url) => replaced.push({ state, url }) },
  };
  mod.clearOriginMarker();
  eq('marker is stripped, real params and hash kept', replaced.map((r) => r.url), ['/menu?campus=futa#top']);
  eq('history state is preserved', replaced.map((r) => r.state), [{ keep: true }]);

  const untouched = [];
  globalThis.window = {
    location: at('holygrills.online', '/menu', '?campus=futa'),
    history: { state: null, replaceState: (_s, _t, url) => untouched.push(url) },
  };
  mod.clearOriginMarker();
  eq('no marker → no history write at all', untouched, []);
}

console.log(failures === 0
  ? 'PASS canonical origin: www alias normalises to https://holygrills.online with path/query/hash intact, '
    + 'every other host untouched, and the guard can never loop (one attempt, bounce-aware, marker stripped)'
  : `${failures} canonical-origin check(s) failed`);
if (failures) process.exit(1);
