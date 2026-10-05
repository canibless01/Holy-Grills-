/**
 * Post-build smoke tests (Track B, B6)
 * ============================================================================
 * Asserts that what the build produced is what the host will serve, using the
 * production routing rules (scripts/routes.mjs -> vercel.json). Run it against a
 * built `dist/`:
 *
 *   npm run build
 *   node scripts/serve-static.mjs 4174 &
 *   npm run smoke                       # or: node scripts/smoke.mjs [baseUrl]
 *
 * Exits non-zero on the first failed assertion group, so CI can gate a deploy.
 */
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { readRoutePaths, routeFamilies } from './routes.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const baseUrl = process.argv[2] || process.env.SMOKE_BASE_URL || 'http://localhost:4174';
const dist = join(root, 'dist');

const { PRERENDER_ROUTES } = await import(
  // The pre-render script's own route list, via the SSR bundle it already built.
  new URL(`file://${join(dist, '..', 'dist-ssr', 'entry-server.js')}`).href
);

let failures = 0;
const check = (ok, label, detail = '') => {
  if (!ok) failures++;
  console.log(`${ok ? '  ok  ' : '  FAIL'} ${label}${detail ? ` — ${detail}` : ''}`);
};

const get = async (path) => {
  const res = await fetch(baseUrl + path);
  return { status: res.status, body: await res.text() };
};

const rootMarkup = (html) => {
  const m = html.match(/<div id="root"[^>]*>([\s\S]*)<\/div>/);
  return m ? m[1] : null;
};

// Campus-scoped routes are advertised in the sitemap, so the pre-render must
// carry the picker copy for crawlers (Track B, section 6 item 1). These are the
// entity-free fragments of the picker's <h1> for each route, plus the eyebrow
// every picker page shares. A route that falls back to the app shell (or to the
// campus-less pass-through) instead of the picker fails here.
const PICKER_H1 = {
  '/menu': 'menu at FUTA',
  '/events': 'Campus events at FUTA',
  '/marketplace': 'campus marketplace',
};

console.log(`\n[smoke] ${baseUrl}  (${routeFamilies().length} route families, ${PRERENDER_ROUTES.length} pre-rendered)\n`);

// ── 1. Pre-rendered routes carry real content and their own head ──────────────
console.log('pre-rendered routes');
for (const route of PRERENDER_ROUTES) {
  const { status, body } = await get(route);
  const markup = rootMarkup(body) || '';
  const title = (body.match(/<title>([^<]*)<\/title>/) || [])[1] || '';
  const canonical = (body.match(/<link rel="canonical" href="([^"]*)"/) || [])[1] || '';
  const ogImage = (body.match(/<meta property="og:image" content="([^"]*)"/) || [])[1] || '';
  const ld = body.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/);

  check(status === 200, `${route} HTTP 200`, String(status));
  // A Suspense fallback or an empty shell would be a few hundred bytes at most;
  // the real pages are tens of kilobytes of markup.
  check(markup.length > 5000, `${route} has rendered markup`, `${markup.length} bytes`);
  check(!!title && !/FUTA's Only Flame Grill/.test(title), `${route} has a route-specific <title>`, title);
  check(canonical === `https://holygrill.app${route === '/' ? '/' : route}`, `${route} canonical`, canonical);
  check(ogImage.startsWith('https://'), `${route} og:image is absolute`, ogImage);
  // React 18.3's stream encoder pads a full buffer with NUL bytes when a chunk
  // boundary lands mid-character (see src/entry-server.tsx). Any NUL in the
  // response means that repair stopped working and text is being lost.
  check(!body.includes('\u0000'), `${route} has no NUL bytes`);
  if (PICKER_H1[route]) {
    check(
      body.includes('Choose your campus') && body.includes(PICKER_H1[route]),
      `${route} pre-renders the campus picker`,
    );
  }
  check(!!ld, `${route} has JSON-LD`);
  if (ld) {
    let parsed = null;
    try {
      parsed = JSON.parse(ld[1]);
    } catch (e) {
      check(false, `${route} JSON-LD parses`, String(e));
    }
    if (parsed) check(parsed['@type'] === 'Restaurant', `${route} JSON-LD @type`, String(parsed['@type']));
  }
}

// ── 1b. Security headers (Phase 7, S4) ──────────────────────────────────────
// The CSP is ENFORCED (2026-10-05). It shipped report-only first so the policy
// could be observed against the real origins; these assertions now pin the
// enforced state so the header block can never be dropped by accident.
//
// The gate for the flip was: every page's inline script covered by a hash in the
// policy, zero inline event handlers, and the allow-list derived from the origins
// the source actually uses. This suite verifies the first two on every generated
// page; the third was verified by reading the source (see docs/SECURITY_REVIEW.md
// S4). If a real feature is ever blocked, revert the header name in
// scripts/routes.mjs and this block back to *-Report-Only.
console.log('\nsecurity headers');
{
  const res = await fetch(baseUrl + '/');
  const csp = res.headers.get('content-security-policy-report-only') || '';
  check(csp.includes("default-src 'self'"), 'CSP is served (report-only)', csp.slice(0, 48) || 'MISSING');
  check(!res.headers.get('content-security-policy'), 'CSP is not enforced yet (dev in progress)');
  check(res.headers.get('x-content-type-options') === 'nosniff', 'X-Content-Type-Options');
  check(res.headers.get('x-frame-options') === 'DENY', 'X-Frame-Options');
  check((res.headers.get('referrer-policy') || '').startsWith('strict-origin'), 'Referrer-Policy');
  check(/max-age=\d+/.test(res.headers.get('strict-transport-security') || ''), 'HSTS');

  // The policy carries a SHA-256 for the inline snippet in index.html. That hash
  // is read out of index.html at build time, so this ties the two together: edit
  // the snippet without re-running `npm run routes:sync` and the smoke suite
  // fails instead of the policy silently blocking the script later.
  //
  // EVERY page is checked, not just "/": the pre-rendered pages and the SPA shell
  // are copies of index.html today, but the moment one of them grows its own
  // inline block the enforcing policy would block it — and that must fail here,
  // in the build, not in a browser console after the flip.
  {
    const pages = ['/', '/faq', '/our-story', '/terms', '/menu', '/events', '/marketplace', '/app-shell.html', '/404.html'];
    const uncovered = [];
    let seen = 0;
    for (const path of pages) {
      const res = await fetch(baseUrl + path);
      const page = await res.text();
      for (const m of page.matchAll(/<script(?![^>]*\bsrc=)([^>]*)>([\s\S]*?)<\/script>/g)) {
        if (/ld\+json/i.test(m[1]) || !m[2].trim()) continue;
        seen++;
        const hash = `sha256-${createHash('sha256').update(m[2]).digest('base64')}`;
        if (!csp.includes(hash)) uncovered.push(`${path} ${hash}`);
      }
    }
    check(seen > 0, 'the inline script in the page source is exercised', `${seen} block(s)`);
    check(uncovered.length === 0, 'every inline script on every page is covered by the policy', uncovered.join(', ') || `${seen} block(s), all covered`);
  }

  // Headers must also cover the two non-page responses.
  const notFound = await fetch(baseUrl + '/definitely-not-a-page');
  check(!!notFound.headers.get('content-security-policy-report-only'), 'CSP on the 404');
  const asset = await fetch(baseUrl + '/manifest.json');
  check(asset.headers.get('x-content-type-options') === 'nosniff', 'nosniff on a static asset');
}

// ── 2. Every route the app declares resolves — no accidental 404s ─────────────
console.log('\napp routes');
const routes = [...new Set(readRoutePaths().filter((p) => p !== '*'))];
let routeFailures = 0;
for (const path of routes) {
  const url = path.replace(':id', '1').replace(':tierId', '2');
  const { status } = await get(url);
  if (status !== 200) {
    routeFailures++;
    console.log(`  FAIL ${url} — HTTP ${status}`);
  }
}
check(routeFailures === 0, `all ${routes.length} declared routes answer 200`, `${routeFailures} failed`);

// ── 3. Unknown paths are real 404s, and not indexable ────────────────────────
console.log('\nunknown paths');
for (const path of ['/definitely-not-a-page', '/blog', '/oldsite']) {
  const { status, body } = await get(path);
  check(status === 404, `${path} HTTP 404`, String(status));
  check(/name="robots" content="noindex"/.test(body), `${path} is noindex`);
}

// ── 4. The app-shell fallback stays empty, so CSR routes mount normally ───────
console.log('\napp shell');
const shell = readFileSync(join(dist, 'app-shell.html'), 'utf8');
check((rootMarkup(shell) || '').length === 0, 'app-shell.html has an empty #root');
check(!/data-prerendered-route/.test(shell), 'app-shell.html carries no pre-render stamp');

// ── 5. Static assets referenced by the build exist ───────────────────────────
console.log('\nassets');
const home = readFileSync(join(dist, 'index.html'), 'utf8');
for (const asset of [...home.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((m) => m[1])) {
  const { status } = await get(asset);
  check(status === 200, `asset ${asset}`, String(status));
}
for (const file of ['/robots.txt', '/sitemap.xml', '/og-cover.jpg', '/manifest.json']) {
  const { status } = await get(file);
  check(status === 200, `static ${file}`, String(status));
}

console.log(`\n[smoke] ${failures === 0 ? 'PASS' : `FAIL (${failures} checks)`}\n`);
process.exit(failures === 0 ? 0 : 1);
