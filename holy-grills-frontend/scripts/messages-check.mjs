/**
 * messages-check — the guard between frontend copy and the backend registry.
 * ============================================================================
 * The frontend renders its own copy through `msg('FE_KEY', '<fallback>')`
 * (src/lib/messages.ts), and the authoritative text lives in
 * `holy-grills-backend/app/messages.py` under the `FE_` keys, served by
 * `GET /api/messages`.
 *
 * This check keeps the two in step:
 *   • ERROR — a `msg('FE_…')` call site whose key is missing from the registry.
 *     (That would silently render the fallback forever, so the copy could never
 *     be reworded from the backend.)
 *   • WARN  — fallback text that no longer matches the registry. Authoritative
 *     text is the registry (reword it and the app follows), so this is drift to
 *     clean up when convenient, not a broken build.
 *   • WARN  — `FE_` keys in the registry no call site uses yet.
 *
 * Run: `npm run messages:check` (part of `npm run build`). Skips with a note when
 * the backend checkout is not present next to the frontend.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname, extname } from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const registryPath = join(repoRoot, '..', 'holy-grills-backend', 'app', 'messages.py');

let registry;
try {
  registry = readFileSync(registryPath, 'utf8');
} catch {
  console.log('[messages] backend registry not found — skipping (frontend-only checkout).');
  process.exit(0);
}

/** key → text for every single-line FE_ constant in the Python registry. */
const registryKeys = new Map();
for (const match of registry.matchAll(/^\s{4}(FE_[A-Z0-9_]+)\s*=\s*"((?:[^"\\]|\\.)*)"\s*$/gm)) {
  registryKeys.set(match[1], unescapePython(match[2]));
}

/** Every `msg('FE_…', '…')` call in the frontend source. */
const callSites = [];
const walk = (dir) => {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) { walk(path); continue; }
    if (!['.ts', '.tsx'].includes(extname(path))) continue;
    const source = readFileSync(path, 'utf8');
    // The fallback may be single- OR double-quoted (copy often contains an apostrophe).
    for (const match of source.matchAll(/\bmsg\(\s*'(FE_[A-Z0-9_]+)'\s*,\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")/g)) {
      const line = source.slice(0, match.index).split('\n').length;
      callSites.push({
        key: match[1],
        fallback: unescapeJs(match[2] !== undefined ? match[2] : match[3]),
        where: `${path.replace(repoRoot + '/', '')}:${line}`,
      });
    }
  }
};
walk(join(repoRoot, 'src'));

function unescapePython(text) {
  return text.replace(/\\"/g, '"').replace(/\\'/g, "'").replace(/\\n/g, '\n');
}
function unescapeJs(text) {
  return text.replace(/\\'/g, "'").replace(/\\"/g, '"').replace(/\\n/g, '\n');
}

const missing = callSites.filter((site) => !registryKeys.has(site.key));
const drifted = callSites.filter((site) => registryKeys.has(site.key) && registryKeys.get(site.key) !== site.fallback);
const unused = [...registryKeys.keys()].filter((key) => !callSites.some((site) => site.key === key));

console.log(`\n[messages] ${callSites.length} frontend call site(s) · ${registryKeys.size} FE_ key(s) in the registry`);

for (const site of drifted) {
  console.log(`  drift  ${site.where}  ${site.key}`);
  console.log(`         frontend fallback: ${JSON.stringify(site.fallback)}`);
  console.log(`         registry:          ${JSON.stringify(registryKeys.get(site.key))}`);
}
if (unused.length) console.log(`  note   registry keys not used yet: ${unused.sort().join(', ')}`);

if (missing.length) {
  for (const site of missing) {
    console.log(`  FAIL   ${site.where}  ${site.key} is not defined in app/messages.py`);
  }
  console.log(`\n[messages] FAIL — ${missing.length} key(s) missing from the registry.\n`);
  process.exit(1);
}

console.log(`  ok     every call site resolves against the registry${drifted.length ? ` (${drifted.length} drifted fallback(s))` : ''}\n`);
