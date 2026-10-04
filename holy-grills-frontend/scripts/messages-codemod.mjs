#!/usr/bin/env node
/**
 * messages-codemod — move hardcoded user-facing strings onto the backend copy
 * registry (GET /api/messages) in bulk.
 * ============================================================================
 * Only three call shapes are touched, and only when the message is a PLAIN
 * string literal (no `${}` interpolation — those need a human who can name the
 * placeholders):
 *
 *     toast({ title: 'Saved', description: 'All good.', variant: '...' })
 *         -> toast({ title: msg('FE_..._SAVED', 'Saved'), description: msg('FE_...', 'All good.') })
 *     setError('Enter a name')
 *         -> setError(msg('FE_..._ENTER_A_NAME', 'Enter a name'))
 *     throw new Error('Nope')
 *         -> throw new Error(msg('FE_..._NOPE', 'Nope'))
 *
 * `toast(...)` bodies are found with a small scanner (string/comment aware) so
 * nested objects, JSX and `)` inside strings cannot confuse it; `title:` keys
 * OUTSIDE a toast call (page metadata, legal copy, list rows) are deliberately
 * left alone — they are content, not messages.
 *
 * Keys are derived from the file and a slug of the text
 * (`src/pages/Menu.tsx` + "Item added" -> `FE_MENU_ITEM_ADDED`). Identical text
 * in the same file reuses one key; the suffix `_2`, `_3`, ... disambiguates a
 * collision with an existing registry entry.
 *
 * The fallback passed to `msg()` is the ORIGINAL literal, byte for byte, so this
 * tool cannot paraphrase anything. `npm run messages:check` then fails the
 * build unless every generated key exists in the backend registry — that is the
 * safety net for this script.
 *
 * Usage:
 *   node scripts/messages-codemod.mjs --dry            # report only
 *   node scripts/messages-codemod.mjs --write          # rewrite src/
 *   node scripts/messages-codemod.mjs --write --files a,b
 *   node scripts/messages-codemod.mjs --manifest out.json   # key/text/file map
 */
import { readFileSync, writeFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, extname } from 'node:path';

const ROOT = new URL('..', import.meta.url).pathname.replace(/\/$/, '');
const SRC = join(ROOT, 'src');
const REGISTRY = join(ROOT, '../holy-grills-backend/app/messages.py');

const args = process.argv.slice(2);
const WRITE = args.includes('--write');
const onlyArg = args.find((a) => a.startsWith('--files'));
const ONLY = onlyArg ? (args[args.indexOf(onlyArg) + 1] || '').split(',').filter(Boolean) : null;
const manifestArg = args.indexOf('--manifest');
const MANIFEST = manifestArg >= 0 ? args[manifestArg + 1] : null;

/** Every .ts/.tsx under src/ (the crawl order is stable so keys never shuffle). */
function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir).sort()) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else if (['.ts', '.tsx'].includes(extname(p))) out.push(p);
  }
  return out;
}

/**
 * Skip over a string / template literal / comment starting at `i`.
 * Returns the index just past it, or -1 when the char at `i` starts nothing.
 */
function skipToken(s, i) {
  const c = s[i];
  if (c === '"' || c === "'") {
    i++;
    while (i < s.length) {
      if (s[i] === '\\') i += 2;
      else if (s[i] === c) return i + 1;
      else i++;
    }
    return s.length;
  }
  if (c === '`') {
    i++;
    while (i < s.length) {
      if (s[i] === '\\') i += 2;
      else if (s[i] === '`') return i + 1;
      else i++;
    }
    return s.length;
  }
  if (c === '/' && s[i + 1] === '/') {
    const nl = s.indexOf('\n', i);
    return nl === -1 ? s.length : nl;
  }
  if (c === '/' && s[i + 1] === '*') {
    const end = s.indexOf('*/', i + 2);
    return end === -1 ? s.length : end + 2;
  }
  return -1;
}

/** Bounds of every `toast(...)` call body in `s`. */
function toastBodies(s) {
  const bodies = [];
  const re = /\btoast\s*\(/g;
  let m;
  while ((m = re.exec(s))) {
    const open = m.index + m[0].length - 1; // the "("
    let i = open + 1;
    let depth = 1;
    while (i < s.length && depth > 0) {
      const skipped = skipToken(s, i);
      if (skipped !== -1) {
        i = skipped;
        continue;
      }
      if (s[i] === '(') depth++;
      else if (s[i] === ')') depth--;
      i++;
    }
    bodies.push([open + 1, i - 1]);
    re.lastIndex = i;
  }
  return bodies;
}

const PLAIN = String.raw`'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"`;
const KEYED = new RegExp(String.raw`\b(title|description)\s*:\s*(${PLAIN})`, 'g');
const SET_ERROR = new RegExp(String.raw`\bsetError\(\s*(${PLAIN})\s*\)`, 'g');
const THROW_ERROR = new RegExp(String.raw`\bthrow new Error\(\s*(${PLAIN})\s*\)`, 'g');

const snake = (x) =>
  x
    .replace(/\.(tsx?|mjs|js)$/i, '')
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/[^A-Za-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .toUpperCase();

/** "can\\'t" -> "can't" — the registry stores rendered text, not JS source. */
function unescapeJs(text) {
  const map = { n: '\n', t: '\t', r: '\r', "'": "'", '"': '"', '\\': '\\', '`': '`', $: '$' };
  return text.replace(/\\(u[0-9a-fA-F]{4}|.)/g, (_, esc) =>
    esc[0] === 'u' ? String.fromCharCode(parseInt(esc.slice(1), 16)) : (map[esc] ?? esc),
  );
}

/** "You're in ❤️🔥" -> "YOU_RE_IN" */
function textSlug(literal) {
  const inner = literal.slice(1, -1).replace(/\\(.)/g, '$1');
  let slug = snake(inner);
  if (slug.length > 40) slug = slug.slice(0, 40).replace(/_[A-Z0-9]*$/, '');
  return slug;
}

/** Literals already registered, so a generated key never collides. */
function existingKeys() {
  try {
    const py = readFileSync(REGISTRY, 'utf8');
    return new Set([...py.matchAll(/^\s{4}([A-Z][A-Z0-9_]*)\s*=/gm)].map((m) => m[1]));
  } catch {
    return new Set();
  }
}

const keysUsed = existingKeys();
const taken = new Set();
const manifest = [];
const perFile = [];

for (const file of walk(SRC)) {
  const rel = relative(ROOT, file);
  if (rel.includes('lib/messages.ts')) continue;
  if (ONLY && !ONLY.some((o) => rel.endsWith(o))) continue;

  const original = readFileSync(file, 'utf8');
  // A file that binds `msg` itself cannot take the helper under that name —
  // left for a human (there are five such files; four were renamed inline).
  if (/\b(?:const|let|var|function)\s+msg\b/.test(original)) {
    perFile.push({ rel, skipped: 'local `msg` binding — convert by hand' });
    continue;
  }

  /** Replacements applied per source offset, right-to-left. */
  const edits = [];
  const keyFor = new Map(); // literal -> key (same text in one file shares a key)

  const key = (literal) => {
    if (keyFor.has(literal)) return keyFor.get(literal);
    const base = `FE_${snake(rel.split('/').pop().replace(/\.tsx?$/, ''))}_${textSlug(literal) || 'MESSAGE'}`;
    let candidate = base;
    let n = 2;
    while (keysUsed.has(candidate) || taken.has(candidate)) candidate = `${base}_${n++}`;
    keysUsed.add(candidate);
    taken.add(candidate);
    keyFor.set(literal, candidate);
    // The registry holds the RENDERED text, not the JS source literal: a
    // `can\'t` in the source has to land as `can't` (json.dumps in the
    // backend append re-escapes it for Python).
    manifest.push({ key: candidate, text: unescapeJs(literal.slice(1, -1)), file: rel });
    return candidate;
  };

  for (const [start, end] of toastBodies(original)) {
    const body = original.slice(start, end);
    for (const m of body.matchAll(KEYED)) {
      edits.push({ at: start + m.index, len: m[0].length, next: `${m[1]}: msg('${key(m[2])}', ${m[2]})` });
    }
  }
  for (const re of [SET_ERROR, THROW_ERROR]) {
    for (const m of original.matchAll(re)) {
      const literal = m[1];
      const next = m[0].replace(literal, `msg('${key(literal)}', ${literal})`);
      edits.push({ at: m.index, len: m[0].length, next });
    }
  }
  if (!edits.length) continue;

  edits.sort((a, b) => b.at - a.at);
  let out = original;
  for (const e of edits) out = out.slice(0, e.at) + e.next + out.slice(e.at + e.len);

  // Import the helper once; keep an existing import line's shape.
  if (!out.includes("from '@/lib/messages'")) {
    const imports = [...out.matchAll(/^import .*?;$/gm)];
    const last = imports[imports.length - 1];
    const line = `import { msg } from '@/lib/messages';`;
    out = last ? out.slice(0, last.index + last[0].length) + '\n' + line + out.slice(last.index + last[0].length) : `${line}\n${out}`;
  }

  perFile.push({ rel, sites: edits.length, keys: keyFor.size });
  if (WRITE) writeFileSync(file, out);
}

const sites = perFile.reduce((n, f) => n + (f.sites || 0), 0);
console.log(`[messages-codemod] ${WRITE ? 'wrote' : 'dry run'}: ${perFile.length} file(s), ${sites} site(s), ${manifest.length} new key(s)`);
for (const f of perFile.sort((a, b) => (b.sites || 0) - (a.sites || 0))) {
  console.log(f.skipped ? `  skip  ${f.rel} — ${f.skipped}` : `  ${String(f.sites).padStart(3)}  ${f.rel}  (${f.keys} key${f.keys === 1 ? '' : 's'})`);
}
if (MANIFEST) {
  writeFileSync(MANIFEST, JSON.stringify(manifest, null, 2));
  console.log(`[messages-codemod] manifest -> ${MANIFEST}`);
}
