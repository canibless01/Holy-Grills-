/**
 * safeNavigation policy tests (Phase 7, S1/S7/S8)
 * ============================================================================
 * The helpers in src/lib/safeNavigation.ts decide whether the browser is allowed
 * to follow a payment redirect, a rider call link or a CMS link. That policy is
 * security-relevant, so it is exercised here against the real module (esbuild
 * transpiles it; no test framework is added for one file). Run with:
 *
 *   npm run test:safe-navigation
 */
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const out = join(root, 'node_modules', '.cache-safe-navigation.mjs');
execFileSync(join(root, 'node_modules', '.bin', 'esbuild'), [
  join(root, 'src', 'lib', 'safeNavigation.ts'),
  '--loader:.ts=ts',
  '--format=esm',
  `--outfile=${out}`,
]);
writeFileSync(out, readFileSync(out, 'utf8').replace(/from "[^"]*"/g, () => { throw new Error('unexpected import'); }));

// Minimal browser globals the module touches.
let opened = null;
globalThis.window = {
  location: { origin: 'https://holygrill.app', pathname: '/reset-password' },
  open: (url, target, features) => { opened = { url, target, features }; return null; },
};

const { isAllowedPaymentUrl, safeCallHref, openCmsDestination } = await import(out);

let failures = 0;
const eq = (label, got, want) => {
  const ok = got === want;
  if (!ok) failures += 1;
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${ok ? '' : ` — got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`}`);
};

console.log('isAllowedPaymentUrl');
eq('paystack checkout', isAllowedPaymentUrl('https://checkout.paystack.com/abc123'), true);
eq('bare paystack.com', isAllowedPaymentUrl('https://paystack.com/pay/x'), true);
eq('http is refused', isAllowedPaymentUrl('http://checkout.paystack.com/abc'), false);
eq('javascript: is refused', isAllowedPaymentUrl('javascript:alert(1)'), false);
eq('lookalike host is refused', isAllowedPaymentUrl('https://evil-paystack.com/x'), false);
eq('other host is refused', isAllowedPaymentUrl('https://evil.com/x'), false);
eq('empty is refused', isAllowedPaymentUrl(''), false);
eq('non-string is refused', isAllowedPaymentUrl({ url: 'https://checkout.paystack.com' }), false);

console.log('safeCallHref');
eq('tel with spaces', safeCallHref('tel:+234 801 234 5678'), 'tel:+2348012345678');
eq('tel too short', safeCallHref('tel:12'), null);
eq('javascript: is refused', safeCallHref('javascript:alert(1)'), null);
eq('https click-to-chat', safeCallHref('https://wa.me/2348012345678'), 'https://wa.me/2348012345678');
eq('http is refused', safeCallHref('http://wa.me/2348012345678'), null);
eq('garbage is refused', safeCallHref('not a url'), null);

console.log('openCmsDestination');
const navved = [];
const nav = (to) => navved.push(to);
opened = null; navved.length = 0;
openCmsDestination('https://instagram.com/holygrills', nav);
eq('external opens a tab', opened?.url, 'https://instagram.com/holygrills');
eq('external passes noopener', opened?.features, 'noopener,noreferrer');
eq('external does not route', navved.length, 0);
opened = null; navved.length = 0;
openCmsDestination('/menu', nav);
eq('internal routes', navved[0], '/menu');
eq('internal opens no tab', opened, null);
opened = null; navved.length = 0;
openCmsDestination(undefined, nav);
eq('undefined is a no-op', `${navved.length}${opened}`, '0null');
opened = null; navved.length = 0;
openCmsDestination('javascript:alert(1)', nav);
eq('javascript: is not opened as a tab', opened, null);

rmSync(out, { force: true });
console.log(failures === 0 ? '\nHELPER: all assertions pass' : `\nHELPER: ${failures} FAILURES`);
process.exit(failures === 0 ? 0 : 1);
