#!/usr/bin/env python3
"""Frontend <-> backend wiring audit.

Level 1 — path join: every API path the frontend calls, joined against the real
Flask url_map dumped from a booted app (authoritative, not regex).

Level 2 — field join: for write endpoints (POST/PATCH/PUT/DELETE) the JSON keys
the backend reads out of the parsed body are extracted from the view function,
and checked against the keys the frontend call site actually sends. Keys the
backend indexes directly (`data['x']`), guards with `if not data.get('x')`, or
lists in a `required = [...]` array are marked REQUIRED — those are inputs the
UI must collect.

Usage:
    # dump the route map first (see docs/WIRING_AUDIT.md for the snippet)
    python3 tools/wiring_audit.py [--json out.json]
"""
import io
import json
import os
import re
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FE = os.path.join(REPO, 'holy-grills-frontend', 'src')


def _find_routes():
    for cand in (os.path.join(REPO, 'be_routes.json'),
                 '/home/user/be_routes.json',
                 os.path.join(REPO, 'tools', 'be_routes.json')):
        if os.path.exists(cand):
            return cand
    return os.path.join(REPO, 'be_routes.json')


BE_ROUTES = _find_routes()

PARAM_RE = re.compile(r'\$\{[^}]*\}')


def norm_fe(path):
    p = PARAM_RE.sub('{}', path)
    p = re.sub(r'\{[^}]*\}', '{}', p)
    p = re.sub(r'/+', '/', p).rstrip('/') or '/'
    # `…/pdf${qs}` — a template param glued to the end of a segment is an
    # appended query string, not a path segment.
    return re.sub(r'(?<=[A-Za-z0-9_])\{\}$', '', p)


def norm_be(rule):
    p = re.sub(r'<[^>]*:?[^>]*>', '{}', rule)
    p = re.sub(r'^/api(?=/|$)', '', p)
    return re.sub(r'/+', '/', p).rstrip('/') or '/'


# ------------------------------------------------------------- frontend calls
CALL_RE = re.compile(
    r"apiClient\.(getRaw|get|post|patch|put|delete|upload)\s*\(\s*`([^`]+)`|"
    r"apiClient\.(getRaw|get|post|patch|put|delete|upload)\s*\(\s*'([^']+)'|"
    r"apiClient\.(getRaw|get|post|patch|put|delete|upload)\s*\(\s*\"([^\"]+)\"|"
    r"fetch\(\s*`\$\{BASE_URL\}([^`]+)`|"
    r"fetch\(\s*`\$\{API_BASE_URL\}([^`]+)`"
)


def frontend_calls():
    calls = []
    for root, _dirs, files in os.walk(FE):
        for f in files:
            if not f.endswith(('.ts', '.tsx')):
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, REPO)
            src = io.open(full, encoding='utf-8').read()
            lines = src.split('\n')
            for i, line in enumerate(lines, start=1):
                for m in CALL_RE.finditer(line):
                    method = m.group(1) or m.group(3) or m.group(5)
                    path = m.group(2) or m.group(4) or m.group(6)
                    if path is None:
                        path = m.group(7) or m.group(8)
                        method = 'get'
                        for look in lines[i:i + 4]:
                            mm = re.search(r"method:\s*['\"](\w+)", look)
                            if mm:
                                method = mm.group(1)
                                break
                    method = {'getRaw': 'GET'}.get(method, method.upper())
                    calls.append({'method': method, 'path': path,
                                  'norm': norm_fe(path), 'file': rel, 'line': i})
    return calls


# liveApi structure: `const orders = {` … `};`, methods `async create(...) { … }`.
GROUP_RE = re.compile(r'^const (\w+) = \{')
METHOD_RE = re.compile(r'^\s*async (\w+)\s*\(')


def liveapi_methods(liveapi_path):
    """(group, method) → (start_line, body_lines)."""
    src = io.open(liveapi_path, encoding='utf-8').read().split('\n')
    out, group, cur, cur_start = {}, None, None, None
    for i, line in enumerate(src, start=1):
        g = GROUP_RE.match(line)
        if g:
            group = g.group(1)
        m = METHOD_RE.match(line)
        if m and group:
            if cur:
                out[cur] = (cur_start, src[cur_start - 1:i - 1])
            cur, cur_start = (group, m.group(1)), i
    if cur:
        out[cur] = (cur_start, src[cur_start - 1:])
    return out


def _balanced(text, start):
    """Read a balanced (…) argument list from `text` beginning at `start`."""
    depth, i = 0, start
    while i < len(text):
        ch = text[i]
        if ch in '({[':
            depth += 1
        elif ch in ')}]':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        elif ch in '"\'`':
            quote = ch
            i += 1
            while i < len(text) and text[i] != quote:
                i += 2 if text[i] == '\\' else 1
        i += 1
    return text[start:start + 400]


KEY_RE = re.compile(r"[,{(]\s*(\w+)\s*:|^\s*(\w+)\s*,")


def object_keys(text):
    keys = set()
    for m in re.finditer(r"(?<![\w.'\"`])(\w+)\s*:(?!\s*//)", text):
        keys.add(m.group(1))
    for m in re.finditer(r"[{,]\s*(\w+)\s*[,}]", text):     # shorthand { a, b }
        keys.add(m.group(1))
    return keys


def call_site_arg_keys(group, method):
    """Keys the frontend sends for liveApi.<group>.<method>(…)."""
    pat = re.compile(rf"\.{re.escape(group)}\.{re.escape(method)}\s*\(")
    found = {}
    for root, _d, files in os.walk(FE):
        for f in files:
            if not f.endswith(('.ts', '.tsx')):
                continue
            full = os.path.join(root, f)
            text = io.open(full, encoding='utf-8').read()
            lines = text.split('\n')
            for m in pat.finditer(text):
                line_no = text[:m.start()].count('\n') + 1
                rel = os.path.relpath(full, REPO)
                arg = _balanced(text, m.end() - 1)[1:-1]
                keys, how = set(), 'inline'
                if '{' in arg:
                    keys = object_keys(arg)
                else:
                    var = arg.strip().split('(')[0].strip()
                    if re.fullmatch(r'\w+', var or ''):
                        # find `var = {…}` (or `var: {…}`) in the 70 lines above
                        window = '\n'.join(lines[max(0, line_no - 70):line_no])
                        mm = re.search(rf"\b{re.escape(var)}\s*[:=]\s*\{{", window)
                        if mm:
                            keys = object_keys(_balanced(window, mm.end() - 1))
                            how = f'var {var}'
                        elif re.search(rf"\b{re.escape(var)}\b", window):
                            how = f'var {var} (opaque)'
                found[f"{rel}:{line_no}"] = (keys, how)
    return found


# --------------------------------------------------------- backend field reads
GETJSON_RE = re.compile(r"(\w+)\s*=\s*request\.get_json\([^)]*\)")
HELPER_RE = re.compile(r"(\w+)\s*=\s*get_json_object\(\)")


def backend_body(route):
    f = os.path.join(REPO, route['file'])
    if not os.path.exists(f) or not route.get('line'):
        return ''
    lines = io.open(f, encoding='utf-8').read().split('\n')
    start = route['line'] - 1
    body = []
    for i in range(start + 1, min(start + 320, len(lines))):
        line = lines[i]
        if i > start + 3 and re.match(r'^(@\w|def )', line):
            break
        body.append(line)
    return '\n'.join(body)


def backend_reads(route):
    """(all JSON keys read, required keys) for a view function."""
    text = backend_body(route)
    holder = None
    m = GETJSON_RE.search(text) or HELPER_RE.search(text)
    if m:
        holder = m.group(1)
    elif 'request.get_json' in text:
        holder = 'request.get_json()'

    reads, required, indexed = set(), set(), set()
    if holder:
        alias = re.findall(rf"(\w+)\s*=\s*{re.escape(holder)}\s+or\s*\{{", text)
        for n in [holder] + alias:
            for mm in re.finditer(rf"{re.escape(n)}\.get\(\s*['\"](\w+)['\"]", text):
                reads.add(mm.group(1))
            # direct index access, but not an assignment (`data['x'] = …`)
            for mm in re.finditer(rf"{re.escape(n)}\[\s*['\"](\w+)['\"]\s*\](?!\s*=[^=])", text):
                reads.add(mm.group(1))
                indexed.add(mm.group(1))

    # `if not data.get('x')` / `if 'x' not in data` / `if data.get('x') is None`
    for pat in (r"if\s+not\s+\w+\.get\(\s*['\"](\w+)['\"]",
                r"if\s+['\"](\w+)['\"]\s+not\s+in\s+\w+",
                r"if\s+\w+\.get\(\s*['\"](\w+)['\"]\s*\)\s+is\s+None"):
        for mm in re.finditer(pat, text):
            required.add(mm.group(1))

    # explicit `required = ["a", "b"]` lists
    for mm in re.finditer(r"required\s*=\s*\[([^\]]+)\]", text):
        for k in re.findall(r"['\"](\w+)['\"]", mm.group(1)):
            reads.add(k)
            required.add(k)

    # swagger docstring `required: [a, b]`
    for mm in re.finditer(r"required:\s*\[([^\]]+)\]", text):
        for k in re.findall(r"([\w]+)", mm.group(1)):
            required.add(k)
    required -= {k for k in indexed} - required
    return sorted(reads), sorted(required), sorted(indexed)


def frontend_identifiers():
    """Every identifier that appears anywhere in the frontend source — a key
    the UI cannot possibly send if the string never occurs at all."""
    ids = set()
    for root, _dirs, files in os.walk(FE):
        for f in files:
            if f.endswith(('.ts', '.tsx')):
                ids |= set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*',
                                      io.open(os.path.join(root, f), encoding='utf-8').read()))
    return ids


def main():
    routes = json.load(open(BE_ROUTES)) if os.path.exists(BE_ROUTES) else []
    fe_ids = frontend_identifiers()
    calls = frontend_calls()
    liveapi = os.path.join(FE, 'lib', 'liveApi.ts')
    methods = liveapi_methods(liveapi)

    # A Flask <param> matches any single literal segment, so matching is done
    # segment-wise with {} as a wildcard.
    def segments(path):
        return [x for x in path.split('/') if x != '']

    by_method = defaultdict(list)
    for r in routes:
        for m in r['methods']:
            by_method[m].append(r)

    def matches(rule_segs, call_segs):
        if len(rule_segs) != len(call_segs):
            return False
        return all(rs == '{}' or cs == '{}' or rs == cs
                   for rs, cs in zip(rule_segs, call_segs))

    matched_be, unmatched_fe = set(), []
    for c in calls:
        if not c['path'].startswith('/'):
            continue                                # template noise
        hit = [r for r in by_method.get(c['method'], [])
               if matches(segments(norm_be(r['rule'])), segments(c['norm']))]
        if hit:
            for r in hit:
                matched_be.add(id(r))
        else:
            unmatched_fe.append(c)

    ignored = ('/api/webhooks', '/api/docs', '/apidocs')
    unmatched_be = [r for r in routes
                    if id(r) not in matched_be
                    and not r['rule'].startswith(ignored)
                    and 'site-packages' not in (r['file'] or '')]

    # ---- field level: writes only
    # index: (group, method) → def start line, so a call line can claim it
    def_owner = {}
    for (g, m), (start, body) in methods.items():
        for off, bl in enumerate(body):
            def_owner.setdefault(start + off, (g, m, bl))

    report = {'path_level': {'unmatched_frontend_calls': unmatched_fe,
                             'unmatched_backend_routes': unmatched_be},
              'write_field_checks': []}
    for c in calls:
        if c['method'] == 'GET':
            continue
        owner = def_owner.get(c['line'])
        if not owner or c['path'] not in owner[2]:
            continue
        group, method = owner[0], owner[1]
        route = next((r for r in by_method.get(c['method'], [])
                      if matches(segments(norm_be(r['rule'])), segments(c['norm']))), None)
        if not route:
            continue
        reads, required, indexed = backend_reads(route)
        sites = call_site_arg_keys(group, method)
        fe_keys = set()
        for keys, _how in sites.values():
            fe_keys |= keys
        report['write_field_checks'].append({
            'call': f"{c['method']} {c['path']}",
            'backend': f"{route['file']}:{route['line']} {route['func']}",
            'backend_reads': reads,
            'backend_required': required,
            'backend_indexed': indexed,
            'fe_method': f"liveApi.{group}.{method}",
            'fe_call_sites': {k: sorted(v[0]) for k, v in sites.items()},
            'required_missing': [k for k in required if k not in fe_keys],
            'required_never_in_fe_source': [k for k in required if k not in fe_ids],
        })

    if '--json' in sys.argv:
        idx = sys.argv.index('--json')
        json.dump(report, open(sys.argv[idx + 1], 'w'), indent=1)
        print('wrote', sys.argv[idx + 1])

    print(f"frontend calls: {len(calls)}   backend routes: {len(routes)}")
    print(f"\nFE calls with NO backend route: {len(unmatched_fe)}")
    for c in unmatched_fe:
        print(f"  {c['method']:6} {c['path']:50} {c['file']}:{c['line']}")
    print(f"\nBackend routes with NO frontend caller: {len(unmatched_be)}")
    for r in unmatched_be:
        print(f"  {','.join(r['methods']):10} {r['rule']:58} {r['file']}:{r['line']}")
    gaps = [w for w in report['write_field_checks'] if w['required_missing']]
    print(f"\n[heuristic] write endpoints whose REQUIRED fields were not found in the "
          f"call-site window: {len(gaps)} / {len(report['write_field_checks'])} "
          f"(indirect call sites are false positives — see --json)")
    hard = [w for w in report['write_field_checks'] if w['required_never_in_fe_source']]
    print(f"\n[strong] REQUIRED backend fields whose name never appears anywhere in the "
          f"frontend source: {len(hard)}")
    for w in hard:
        print(f"  {w['call']:52} never_in_fe={w['required_never_in_fe_source']}")
        print(f"      {w['backend']}")


if __name__ == '__main__':
    main()
