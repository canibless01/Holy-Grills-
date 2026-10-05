/**
 * Pre-render entry (Track B)
 * ============================================================================
 * Renders one public route to HTML at BUILD time. Nothing here runs in
 * production: `scripts/prerender.mjs` imports this module after
 * `vite build --ssr`, writes `dist/<route>/index.html`, and Vercel serves those
 * files ahead of the SPA fallback.
 *
 * Deliberate properties:
 *   - No data fetching. Effects do not run during render, so the HTML carries
 *     the page's static content and the guest shell only — never user data,
 *     never prices that could go stale in a cache.
 *   - Same provider tree as the browser entry (AppProviders + AppShell), so the
 *     client hydrates into identical markup.
 *   - StaticRouter (react-router-dom/server) because there is no browser URL.
 *   - renderToPipeableStream with onAllReady: the app code-splits every page
 *     with React.lazy, and the legacy renderToString cannot wait for Suspense —
 *     it would emit the loading fallback instead of the page. Waiting for
 *     "all ready" produces the fully resolved markup for the requested route.
 */
import React from 'react';
import { Writable } from 'node:stream';
import { renderToPipeableStream } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom/server';
import { AppProviders, AppShell } from '@/App';

// Re-exported so scripts/prerender.mjs can read the same objects it renders
// with straight out of the SSR bundle (no duplicate metadata in build tooling).
export { ROUTE_META, PRERENDER_ROUTES, headFor, SITE_ORIGIN } from '@/seo/routeMeta';

/**
 * React 18.3 writes its whole 2 KB encoder view to the destination whenever a
 * multi-byte character does not fit in what is left of that view
 * (react-dom-server.node.js, `writeStringChunk`: `writeToDestination(
 * destination, currentView)` without `.subarray(0, writtenBytes)`). The unused
 * tail of the view is zero-filled, so the byte stream carries stray NUL bytes
 * wherever a chunk boundary lands mid-character — and the character itself
 * lands in the next view. Observed in this project: the ❤️‍🔥 in the homepage
 * strapline came out of the /menu pre-render as `\0\0🔥`.
 *
 * The padding is always the *tail* of the offending view, never interior
 * padding (verified against a 500-block stress render), so trimming trailing
 * NUL bytes from each chunk restores exactly the bytes React meant to write.
 * HTML cannot legitimately contain U+0000, and the guard below fails the build
 * if one survives, so a silent regression is not possible.
 */
function trimViewPadding(chunk: Buffer): Buffer {
  let end = chunk.length;
  while (end > 0 && chunk[end - 1] === 0) end -= 1;
  return end === chunk.length ? Buffer.from(chunk) : Buffer.from(chunk.subarray(0, end));
}

/** Render one URL to a complete HTML string. */
export function render(url: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    const sink = new Writable({
      write(chunk, _encoding, callback) {
        const buffer = Buffer.isBuffer(chunk)
          ? chunk
          // Node hands us a Buffer for React's Uint8Array views, but keep the
          // Uint8Array branch so a future Node change cannot silently skip the
          // repair below.
          : Buffer.from(chunk.buffer, chunk.byteOffset, chunk.byteLength);
        chunks.push(trimViewPadding(buffer));
        callback();
      },
    });

    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      const html = Buffer.concat(chunks).toString('utf8');
      if (html.includes('\u0000')) {
        reject(new Error(`[ssr] ${url}: NUL byte survived the encoder-view repair`));
        return;
      }
      resolve(html);
    };

    const { pipe, abort } = renderToPipeableStream(
      <AppProviders>
        <StaticRouter location={url}>
          <AppShell />
        </StaticRouter>
      </AppProviders>,
      {
        // Build-time render: a route that cannot finish in 30s is a bug worth
        // failing the build over rather than shipping an empty page.
        onAllReady() {
          sink.on('finish', finish);
          sink.on('error', reject);
          pipe(sink);
        },
        onError(error) {
          // Recoverable errors (a component's error boundary caught it) still
          // produce usable HTML; only a fatal one leaves us with nothing, and
          // the timeout below catches that.
          console.error(`[ssr] ${url}: ${error instanceof Error ? error.message : String(error)}`);
        },
      },
    );

    const timer = setTimeout(() => {
      abort();
      if (!settled) { settled = true; reject(new Error(`[ssr] ${url}: render timed out`)); }
    }, 30000);
  });
}
