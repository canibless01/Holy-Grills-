/**
 * Route families + host routing config (Track B, B5)
 * ============================================================================
 * The app is a single-page app served by a static host, so the host has to know
 * which paths belong to the SPA. Today it answers 200 for EVERY path (a "soft
 * 404"): /blog, /oldsite, /anything all render the app shell.
 *
 * Fixing that needs three things, and they must stay in sync:
 *
 *   1. `vercel.json` lists the SPA's route families, ending in a real
 *      404 response. Only the legacy `routes` dialect can return a
 *      status code — modern `rewrites` cannot (Vercel docs + community
 *      discussion #9567 both confirm this).
 *   2. `scripts/sync-routes.mjs --check` fails the build if App.tsx grows a
 *      route that is not in that list, so a new page can never silently 404.
 *   3. `scripts/serve-static.mjs` runs the exact same list locally, so what
 *      gets verified in this sandbox is what the host will do.
 *
 * This module holds the single definition of "a route family" that all three
 * use. App.tsx remains the source of truth for the routes themselves.
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const repoRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
export const configPath = join(repoRoot, 'vercel.json');
export const appPath = join(repoRoot, 'src', 'App.tsx');

/** Every `path="..."` in App.tsx, in source order. */
export function readRoutePaths() {
  const src = readFileSync(appPath, 'utf8');
  const paths = [...src.matchAll(/<Route\s+path="([^"]*)"/g)].map((m) => m[1]);
  if (paths.length === 0) {
    throw new Error('readRoutePaths: no <Route path="..."> found in src/App.tsx');
  }
  return paths;
}

/**
 * The SPA owns the first path segment of every route it declares. One entry per
 * family covers the whole subtree (`/events` also covers `/events/:id` and
 * `/events/tiers/:tierId`), so nested pages never need a config change.
 */
export function routeFamilies(paths = readRoutePaths()) {
  const families = new Set(['/']); // "/" is owned unconditionally
  for (const path of paths) {
    if (path === '*' || path === '' || !path.startsWith('/')) continue;
    const segment = path.split('/')[1]; // '' for "/", 'menu' for "/menu/:id"
    if (segment) families.add(`/${segment}`);
  }
  return [...families].sort((a, b) => (a === '/' ? -1 : b === '/' ? 1 : a.localeCompare(b)));
}

/** The full vercel.json for the frontend. */
export function buildConfig() {
  const families = routeFamilies();
  const routes = [{ handle: 'filesystem' }];

  for (const family of families) {
    if (family === '/') continue; // the "/" route is emitted explicitly as "/" below
    // `/<family>` for the page itself, `/<family>/(.*)` for anything below it
    // (including a trailing slash, which "(.*)" matches as empty).
    routes.push({ src: family, dest: '/app-shell.html' });
    routes.push({ src: `${family}/(.*)`, dest: '/app-shell.html' });
  }

  // Home: pre-rendered at dist/index.html, so it is served by `handle: filesystem`.
  // "/" is still listed here because a request for "/" with a query string or an
  // unusual encoding can miss the filesystem step.
  routes.push({ src: '/', dest: '/app-shell.html' });

  // Anything else is a real 404 — with the app shell as the body so the SPA can
  // still render its own PageNotFound for the visitor.
  routes.push({ src: '/(.*)', status: 404, dest: '/404.html' });

  return {
    installCommand: 'npm ci',
    buildCommand: 'npm run build',
    outputDirectory: 'dist',
    routes,
  };
}

/**
 * Translate a legacy `routes` src pattern into a RegExp. Only the two tokens we
 * emit are supported: `(.*)` (any number of path segments) and `:param`.
 * Anything else throws, so a hand-written exotic pattern fails loudly instead of
 * silently mis-serving routes.
 */
export function patternToRegExp(src) {
  const ANY = '\u0000';
  const PARAM = '\u0001';
  const templated = src
    .replace(/\(([^)]*)\)/g, (match) => (match === '(.*)' ? ANY : match))
    .replace(/:([A-Za-z0-9_]+)/g, PARAM);

  if (/[:*?()]/.test(templated)) {
    throw new Error(`patternToRegExp: unsupported pattern "${src}" (only literals, "(.*)" and ":param")`);
  }

  const escaped = templated.replace(/[.+^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`^${escaped.split(ANY).join('(?:.*)').split(PARAM).join('[^/]+')}$`);
}

/**
 * Resolve a pathname the way the host does:
 *   1. a real file (checked by the caller — it owns the filesystem)
 *   2. the SPA route families
 *   3. the final catch-all (status 404)
 * Returns { type: 'file' | 'rewrite' | 'notfound', dest?, status? }.
 */
export function resolvePath(pathname, config = buildConfig()) {
  for (const route of config.routes) {
    if (route.handle === 'filesystem') continue;
    if (!route.src) continue;
    if (patternToRegExp(route.src).test(pathname)) {
      return route.status
        ? { type: 'notfound', dest: route.dest, status: route.status }
        : { type: 'rewrite', dest: route.dest };
    }
  }
  return { type: 'notfound', dest: '/404.html', status: 404 };
}
