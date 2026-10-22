/**
 * Build-time pre-render (Track B)
 * ============================================================================
 * Runs after `vite build` (client) and `vite build --ssr` (server bundle):
 *
 *   1. imports the SSR bundle and renders each public SEO route to HTML;
 *   2. injects that HTML into the built index.html template (which already
 *      carries the asset <script>/<link> tags and the static JSON-LD);
 *   3. replaces the head with route-specific title/description/canonical/OG/
 *      Twitter tags — the same values the page passes to <SEO> at runtime;
 *   4. writes dist/<route>/index.html (and dist/index.html for "/").
 *
 * Vercel serves a matching static file in preference to the SPA rewrite, so no
 * hosting or Flask change is needed and every other route keeps today's
 * behaviour byte-for-byte.
 *
 * Usage:  node scripts/prerender.mjs
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const distDir = join(root, 'dist');
const ssrEntry = join(root, 'dist-ssr', 'entry-server.js');
const templatePath = join(distDir, 'index.html');

if (!existsSync(templatePath) || !existsSync(ssrEntry)) {
  console.error('[prerender] missing build output. Run the client + SSR builds first.');
  process.exit(1);
}

/**
 * The template must be pristine, but running `npm run prerender` twice without
 * a fresh client build would otherwise leave the previous render inside #root.
 * Normalise it here (anchored on the closing tag immediately before the entry
 * <script>) so the script is idempotent and safe to re-run.
 */
const rawTemplate = readFileSync(templatePath, 'utf8');

// The mount point is everything from <div id="root"> to the document's last
// </div>: Vite puts the entry <script type="module"> in <head>, and the body
// tail (dev-sandbox guard, service-worker cleanup) contains no markup, so index
// math is exact here where a regex would have to guess at nesting.
const rootAt = rawTemplate.indexOf('<div id="root">');
const lastClose = rawTemplate.lastIndexOf('</div>');
const template =
  rootAt !== -1 && lastClose > rootAt
    ? `${rawTemplate.slice(0, rootAt)}<div id="root"></div>${rawTemplate.slice(lastClose + 6)}`
    : null;

if (!template || !template.includes('<div id="root"></div>')) {
  console.error('[prerender] dist/index.html does not look like a fresh client build.');
  console.error('[prerender] Run `npm run build:client` first (npm run build does this for you).');
  process.exit(1);
}
// One import: the SSR bundle carries both the renderer and the route metadata
// (re-exported from src/seo/routeMeta.ts by src/entry-server.tsx).
const { render, PRERENDER_ROUTES: routes, headFor, SITE_ORIGIN } = await import(pathToFileURL(ssrEntry).href);
if (typeof render !== 'function' || !routes || typeof headFor !== 'function') {
  console.error('[prerender] the SSR bundle did not expose render() + route metadata.');
  process.exit(1);
}

const escapeHtml = (s) =>
  String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const replaceTag = (html, pattern, replacement) =>
  pattern.test(html) ? html.replace(pattern, replacement) : html.replace('</head>', `${replacement}\n  </head>`);

const upsertMeta = (html, attr, key, content) => {
  const tag = `<meta ${attr}="${key}" content="${escapeHtml(content)}" />`;
  const re = new RegExp(`<meta[^>]*${attr}="${key}"[^>]*>`, 'i');
  return re.test(html) ? html.replace(re, tag) : html.replace('</head>', `  ${tag}\n  </head>`);
};

const buildHead = (html, route) => {
  const m = headFor(route);
  const canonical = `${SITE_ORIGIN}${m.path}`;
  let out = html;

  out = out.replace(/<title>[\s\S]*?<\/title>/i, `<title>${escapeHtml(m.title)}</title>`);
  out = upsertMeta(out, 'name', 'description', m.description);
  out = upsertMeta(out, 'property', 'og:title', m.title);
  out = upsertMeta(out, 'property', 'og:description', m.description);
  out = upsertMeta(out, 'property', 'og:url', canonical);
  out = upsertMeta(out, 'name', 'twitter:title', m.title);
  out = upsertMeta(out, 'name', 'twitter:description', m.description);
  out = replaceTag(out, /<link[^>]*rel="canonical"[^>]*>/i, `<link rel="canonical" href="${canonical}" />`);

  if (m.image) {
    out = upsertMeta(out, 'property', 'og:image', m.image);
    out = upsertMeta(out, 'name', 'twitter:image', m.image);
  }
  // og:image must be absolute for crawlers; headFor() already resolved it.
  return out;
};

let written = 0;
for (const route of routes) {
  const html = await render(route);
  if (!html || html.length < 50) {
    console.error(`[prerender] empty render for ${route} — refusing to write`);
    process.exit(1);
  }
  const withHead = buildHead(template, route);
  // The data attribute lets src/main.tsx confirm the file matches the URL it is
  // hydrating for (see the hydration gate there).
  const withBody = withHead.replace(
    /<div id="root">\s*<\/div>/,
    `<div id="root" data-prerendered-route="${route}">${html}</div>`,
  );
  if (withBody === withHead) {
    console.error('[prerender] could not find <div id="root"> in the template');
    process.exit(1);
  }

  const outFile = route === '/' ? join(distDir, 'index.html') : join(distDir, route.slice(1), 'index.html');
  mkdirSync(dirname(outFile), { recursive: true });
  writeFileSync(outFile, withBody);
  written++;
  console.log(`[prerender] ${route} -> ${outFile.replace(root + '/', '')} (${html.length} bytes of markup)`);
}

// Everything that is NOT pre-rendered (the ~36 CSR and authed routes) is served
// this empty shell by the host's catch-all rewrite, so the client mounts fresh
// exactly as it did before this workstream. Keeping it separate from
// dist/index.html is what stops /menu from being handed the home page's markup
// and metadata.
const shellFile = join(distDir, 'app-shell.html');
writeFileSync(shellFile, template);
console.log(`[prerender] app shell -> ${shellFile.replace(root + '/', '')} (SPA fallback for all SPA routes)`);

// Unknown paths get a REAL 404 (see vercel.json's final route entry). The body is
// the same shell so the SPA can render its own PageNotFound for the visitor, with
// noindex on top: the URL genuinely does not exist, and a crawler must not index
// the shell for it.
const notFound = template
  .replace(/<title>[\s\S]*?<\/title>/i, '<title>Page not found — Holy Grills</title>')
  .replace('</head>', '  <meta name="robots" content="noindex" />\n  </head>');
const notFoundFile = join(distDir, '404.html');
writeFileSync(notFoundFile, notFound);
console.log(`[prerender] 404 -> ${notFoundFile.replace(root + '/', '')} (served with HTTP 404 for unknown paths)`);

console.log(`[prerender] ${written} route(s) pre-rendered.`);
