/**
 * Keep vercel.json's SPA route list in sync with src/App.tsx (Track B, B5)
 * ============================================================================
 *   node scripts/sync-routes.mjs --write    regenerate vercel.json in place
 *   node scripts/sync-routes.mjs --check    fail if vercel.json is out of date
 *
 * `npm run build` runs --check, so adding a page to App.tsx without syncing is a
 * build error with instructions rather than a page that answers 404 in
 * production.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { buildConfig, configPath, routeFamilies, readRoutePaths, repoRoot } from './routes.mjs';

const mode = process.argv.includes('--write') ? 'write' : 'check';
const expected = buildConfig();
const expectedJson = `${JSON.stringify(expected, null, 2)}\n`;

if (mode === 'write') {
  writeFileSync(configPath, expectedJson);
  console.log(
    `[routes] vercel.json written: ${routeFamilies().length} SPA route families ` +
      `from ${readRoutePaths().length} App.tsx routes`,
  );
} else {
  const current = readFileSync(configPath, 'utf8');
  if (current === expectedJson) {
    console.log(`[routes] vercel.json is in sync (${routeFamilies().length} SPA route families)`);
  } else {
    console.error('[routes] vercel.json is OUT OF DATE with src/App.tsx.');
    console.error('[routes] Run `npm run routes:sync`, then commit the result.');
    const currentFamilies = new Set(
      (JSON.parse(current).routes || [])
        .filter((r) => r.dest === '/app-shell.html' && r.src)
        .map((r) => r.src.replace(/\/\(\.\*\)$/, '')),
    );
    const missing = routeFamilies().filter((f) => !currentFamilies.has(f));
    if (missing.length) console.error(`[routes] missing from vercel.json: ${missing.join(', ')}`);
    process.exit(1);
  }
}

// Keep the file path visible in logs (it lives at the frontend package root).
void repoRoot;
