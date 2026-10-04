/**
 * Static host simulator (Track B)
 * ============================================================================
 * Serves `dist/` the way the production host does, so the pre-rendered files can
 * be verified locally and in CI:
 *
 *   1. exact file              /assets/app.js, /robots.txt, /sitemap.xml
 *   2. directory index         /faq            -> dist/faq/index.html
 *   3. .html suffix            /faq            -> dist/faq.html
 *   4. SPA fallback            anything else   -> dist/index.html (HTTP 200)
 *
 * That order is what makes the pre-render visible: a real file wins, everything
 * else falls through to the app shell exactly as vercel.json's catch-all rewrite
 * does. `vite preview` cannot check this, because it applies the SPA fallback to
 * every route.
 *
 * Usage:  node scripts/serve-static.mjs [port]     (default 4174)
 */
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { dirname, extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const distDir = join(root, 'dist');
const port = Number(process.argv[2] || process.env.PORT || 4174);

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

const server = createServer(async (req, res) => {
  const urlPath = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  // Block traversal before touching the filesystem.
  const rel = normalize(urlPath).replace(/^(\.\.[/\\])+/, '');
  const candidates = [
    join(distDir, rel), // exact file
    join(distDir, rel, 'index.html'), // directory index
    join(distDir, `${rel}.html`), // .html suffix
  ];

  for (const candidate of candidates) {
    if (candidate.startsWith(distDir) && (await isFile(candidate))) {
      const body = await readFile(candidate);
      res.writeHead(200, {
        'Content-Type': MIME[extname(candidate)] || 'application/octet-stream',
        'Content-Length': body.length,
      });
      res.end(body);
      return;
    }
  }

  // SPA fallback (mirrors vercel.json's catch-all rewrite, which points at the
  // pre-render script's empty shell rather than the home page).
  const shell = await readFile(join(distDir, 'app-shell.html'));
  res.writeHead(200, { 'Content-Type': MIME['.html'], 'Content-Length': shell.length });
  res.end(shell);
});

server.listen(port, '0.0.0.0', () => {
  console.log(`[static] serving dist/ on http://0.0.0.0:${port} (file -> index -> .html -> SPA fallback)`);
});
