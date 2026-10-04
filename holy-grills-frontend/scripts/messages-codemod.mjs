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
 *   node scripts/messages-codemod.mjs --dry            # report only (plain literals)
 *   node scripts/messages-codemod.mjs --dry --templates # also the `a ${b}` ones
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
const TEMPLATES = args.includes('--templates');
const skippedTemplates = [];
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

// ── Interpolated messages (`` `Sent to ${name}` ``) ──────────────────────────
// A template literal needs names for its holes, so this pass is separate from
// the plain-literal one and is opt-in (`--templates`). It converts a hole to a
// {placeholder} and passes the expression through as a var:
//
//     toast({ description: `Nudge sent to ${n} carts` })
//       -> toast({ description: msg('FE_…', 'Nudge sent to {count} carts', { count: n }) })
//
// It SKIPS a message whose hole contains its own copy, e.g.
// `${!on ? '✅ Activated' : '⏸ Deactivated'}` — that needs the two variants as
// two registry keys, which is a wording decision, not a rename. Skipped sites
// are printed so they can be done by hand.

/** End index just past the template literal starting at `start` (a backtick). */
function scanTemplate(s, start) {
  let i = start + 1;
  while (i < s.length) {
    const c = s[i];
    if (c === '\\') { i += 2; continue; }
    if (c === '`') return i + 1;
    if (c === '$' && s[i + 1] === '{') {
      let depth = 1;
      i += 2;
      while (i < s.length && depth > 0) {
        const skipped = skipToken(s, i);
        if (skipped !== -1 && s[i] !== '`') { i = skipped; continue; }
        if (s[i] === '{') depth++;
        else if (s[i] === '}') depth--;
        i++;
      }
      continue;
    }
    i++;
  }
  return s.length;
}

/** Every template literal in `s` as [start, end]. */
function findTemplates(s) {
  const found = [];
  let i = 0;
  while (i < s.length) {
    if (s[i] === '`') {
      const end = scanTemplate(s, i);
      found.push([i, end]);
      i = end;
      continue;
    }
    const skipped = skipToken(s, i);
    i = skipped === -1 ? i + 1 : skipped;
  }
  return found;
}

/** `` `a ${b} c` `` -> [{text:'a '},{expr:'b'},{text:' c'}] */
function parseTemplate(inner) {
  const parts = [];
  let buf = '';
  let i = 0;
  while (i < inner.length) {
    const c = inner[i];
    if (c === '\\') { buf += unescapeJs(inner.slice(i, i + 2)); i += 2; continue; }
    if (c === '$' && inner[i + 1] === '{') {
      let depth = 1;
      let j = i + 2;
      while (j < inner.length && depth > 0) {
        const skipped = skipToken(inner, j);
        if (skipped !== -1 && inner[j] !== '`') { j = skipped; continue; }
        if (inner[j] === '{') depth++;
        else if (inner[j] === '}') depth--;
        j++;
      }
      parts.push({ text: buf });
      parts.push({ expr: inner.slice(i + 2, j - 1).trim() });
      buf = '';
      i = j;
      continue;
    }
    buf += c;
    i++;
  }
  parts.push({ text: buf });
  return parts;
}

/**
 * A readable placeholder name for a hole. `purchaseUnitName` -> {purchase_unit_name},
 * `x.toLocaleDateString()` -> {date}, `rows.length` -> {count}, and the handful
 * of names that read better short (name, amount, hp, error, count) are mapped.
 */
function placeholderName(expr) {
  const map = {
    message: 'error', err: 'error',
    amount: 'amount', amt: 'amount', total: 'amount', price: 'amount', fee: 'amount',
    hp_awarded: 'hp', awarded: 'hp', hp: 'hp', balance: 'balance', new_balance: 'balance',
    recipient_name: 'name', full_name: 'name', nickname: 'name', name: 'name',
    credits: 'count', spins: 'count', nudged: 'count', toGo: 'count', over: 'count', size: 'count',
    title: 'title', label: 'prize', prize: 'prize', code: 'code', id: 'id',
  };
  const snake = (x) => x.replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase();

  // A formatted value: the hole is a date/number for the copy to read naturally.
  if (/toLocale(DateString|TimeString|Date|Time|String)\(/.test(expr)) return 'date';
  if (/\.length\b/.test(expr)) return 'count';

  const base = expr.replace(/\.trim\(\)$/, '');
  const last = (base.match(/[A-Za-z_$][\w$]*/g) || []).pop() || 'value';
  const cleaned = last.replace(/^_+/, '') || 'value';
  // Own-property lookup only: `map['toLocaleString']` would otherwise return
  // Object.prototype.toLocaleString (a function) and stringify into the copy.
  const pick = (k) => (Object.prototype.hasOwnProperty.call(map, k) ? map[k] : undefined);
  return pick(expr) || pick(cleaned) || snake(cleaned);
}

/** Escape a rendered string into a single-quoted JS literal. */
const jsLiteral = (text) => "'" + text
  .replace(/\\/g, '\\\\')
  .replace(/'/g, "\\'")
  .replace(/\n/g, '\\n')
  .replace(/\r/g, '\\r')
  .replace(/\t/g, '\\t') + "'";

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
function textSlug(rendered) {
  let slug = snake(rendered);
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

  // The registry holds the RENDERED text, not the JS source literal: a
  // `can\'t` in the source has to land as `can't` (json.dumps in the backend
  // append re-escapes it for Python).
  const keyForText = (rendered) => {
    if (keyFor.has(rendered)) return keyFor.get(rendered);
    const base = `FE_${snake(rel.split('/').pop().replace(/\.tsx?$/, ''))}_${textSlug(rendered) || 'MESSAGE'}`;
    let candidate = base;
    let n = 2;
    while (keysUsed.has(candidate) || taken.has(candidate)) candidate = `${base}_${n++}`;
    keysUsed.add(candidate);
    taken.add(candidate);
    keyFor.set(rendered, candidate);
    manifest.push({ key: candidate, text: rendered, file: rel });
    return candidate;
  };
  const key = (literal) => keyForText(unescapeJs(literal.slice(1, -1)));

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
  // ── interpolated messages ────────────────────────────────────────────────
  if (TEMPLATES) {
    const bodies = toastBodies(original);
    const inToast = (at) => bodies.find(([a, b]) => at >= a && at < b);
    for (const [start, end] of findTemplates(original)) {
      const before = original.slice(Math.max(0, start - 60), start);
      const literal = original.slice(start, end);
      const inner = literal.slice(1, -1);
      const parts = parseTemplate(inner);
      const holes = parts.filter((p) => p.expr);
      // Which call is it? The replaced range is the backtick literal alone, so
      // the emitted text is ONLY the msg(...) call — never the surrounding
      // `title:` / `setError(` prefix.
      const toast = inToast(start);
      const isTitle = toast && /(?:title|description)\s*:\s*$/.test(before);
      const isSetter = /setError\(\s*$/.test(before) || /throw new Error\(\s*$/.test(before);
      if (!isTitle && !isSetter) continue;

      if (!holes.length) {
        // A backtick string with no holes is just a plain string.
        const text = parts.map((p) => p.text).join('');
        edits.push({ at: start, len: literal.length, next: `msg('${keyForText(text)}', ${jsLiteral(text)})` });
        continue;
      }

      // A hole carrying its own copy (a ternary with quoted words) is two
      // messages, not one with a placeholder — a human has to split it.
      if (holes.some((h) => /['"][^'"]*[A-Za-z][^'"]*['"]/.test(h.expr))) {
        skippedTemplates.push(`${rel}:${original.slice(0, start).split('\n').length} ${literal.slice(0, 60)}`);
        continue;
      }

      const used = new Map();
      const vars = [];
      const text = parts.map((p) => {
        if (!p.expr) return p.text;
        let name = placeholderName(p.expr);
        if (!/^[a-z][a-z0-9_]*$/.test(name)) {
          skippedTemplates.push(`${rel}:${original.slice(0, start).split('\n').length} hole \${${p.expr}} -> '${name}'`);
          name = 'value';
        }
        while (used.has(name) && used.get(name) !== p.expr) name = `${name}_${used.size + 1}`;
        used.set(name, p.expr);
        if (!vars.some((v) => v.name === name)) vars.push({ name, expr: p.expr });
        return `{${name}}`;
      }).join('');

      const call = `msg('${keyForText(text)}', ${jsLiteral(text)}, { ${vars.map((v) => `${v.name}: ${v.expr}`).join(', ')} })`;
      edits.push({ at: start, len: literal.length, next: call });
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
if (skippedTemplates.length) {
  console.log(`\n[messages-codemod] ${skippedTemplates.length} interpolated message(s) need a human (a hole carries its own copy):`);
  for (const line of skippedTemplates) console.log(`  - ${line}`);
}
if (MANIFEST) {
  writeFileSync(MANIFEST, JSON.stringify(manifest, null, 2));
  console.log(`[messages-codemod] manifest -> ${MANIFEST}`);
}
