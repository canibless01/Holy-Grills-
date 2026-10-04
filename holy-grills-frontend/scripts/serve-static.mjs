/**
 * Static host simulator (Track B)
 * ============================================================================
 * Serves `dist/` the way the production host does, driven by the real
 * `vercel.json` — so what is verified here is what the host will do:
 *
 *   1. filesystem        exact file, directory index, .html suffix
 *                        (/faq -> dist/faq/index.html)
 *   2. route families    App.tsx's routes -> dist/app-shell.html, HTTP 200
 *   3. anything else     dist/404.html with a REAL HTTP 404
 *
 * `vite preview` cannot check any of this: it applies its own SPA fallback to
 * every path and answers 200.
 *
 * Usage:  node scripts/serve-static.mjs [port]     (default 4174)
 */
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { dirname, extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';
import { readFileSync } from 'node:fs';
import { resolvePath } from './routes.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const distDir = join(root, 'dist');
const port = Number(process.argv[2] || process.env.PORT || 4174);

// Fail at startup rather than serving a half-configured host.
const config = JSON.parse(readFileSync(join(root, 'vercel.json'), 'utf8'));
if (!Array.isArray(config.routes)) {
  console.error('[static] vercel.json has no `routes` array — run `npm run routes:sync`.');
  process.exit(1);
}

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.avif': 'image/avif',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
  '.xml': 'application/xml; charset=utf-8',
};

const isFile = async (p) => {
  try {
    return (await stat(p)).isFile();
  } catch {
    return false;
  }
};

const send = (res, file, status) => {
  const body = readFileSync(file);
  res.writeHead(status, {
    'Content-Type': MIME[extname(file)] || 'text/html; charset=utf-8',
    'Content-Length': body.length,
  });
  res.end(body);
};

const server = createServer(async (req, res) => {
  const urlPath = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  // Block traversal before touching the filesystem.
  const rel = normalize(urlPath).replace(/^(\.\.[/\\])+/, '');
  const candidates = [
    join(distDir, rel), // exact file
    join(distDir, rel, 'index.html'), // directory index
    join(distDir, `${rel}.html`), // .html suffix
  ];

  // Step 1 — `handle: filesystem`.
  for (const candidate of candidates) {
    if (candidate.startsWith(distDir) && (await isFile(candidate))) {
      send(res, candidate, 200);
      return;
    }
  }

  // Steps 2 and 3 — the SPA's route families, then a real 404.
  const resolved = resolvePath(urlPath, config);
  const dest = join(distDir, resolved.dest.replace(/^\//, ''));
  if (!(await isFile(dest))) {
    console.error(`[static] ${urlPath} -> ${resolved.dest} is missing from dist/`);
    send(res, join(distDir, 'app-shell.html'), 500);
    return;
  }
  send(res, dest, resolved.status || 200);
});

server.listen(port, '0.0.0.0', () => {
  console.log(`[static] serving dist/ on http://0.0.0.0:${port} (file -> index -> .html -> SPA fallback)`);
});
