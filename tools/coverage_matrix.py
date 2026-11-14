#!/usr/bin/env python3
"""Build the Flask <-> frontend coverage matrix from both codebases."""
import os, re, json, glob
from collections import OrderedDict

REPO = '/home/user/Holy-Grills-'
BE = os.path.join(REPO, 'holy-grills-backend/app')
FE = os.path.join(REPO, 'holy-grills-frontend/src')

# ---------------------------------------------------------------- backend side
# blueprint variable -> url_prefix, read from app.register_blueprint(...) calls
bp_prefix = {}
_init = open(os.path.join(BE, '__init__.py')).read()
for m in re.finditer(r"register_blueprint\(\s*(\w+)\s*,\s*url_prefix\s*=\s*['\"]([^'\"]+)['\"]", _init):
    bp_prefix[m.group(1)] = m.group(2)
# fallback: prefixes declared on the Blueprint itself
for f in glob.glob(os.path.join(BE, 'routes/*.py')):
    src = open(f).read()
    for m in re.finditer(r"(\w+)\s*=\s*Blueprint\([^)]*url_prefix\s*=\s*['\"]([^'\"]+)['\"]", src):
        bp_prefix.setdefault(m.group(1), m.group(2))

routes = []   # (methods, full_path, file:line, auth)
for f in glob.glob(os.path.join(BE, 'routes/*.py')) + glob.glob(os.path.join(BE, '*.py')) + glob.glob(os.path.join(BE, '**/*.py'), recursive=True):
    src = open(f).read()
    lines = src.split('\n')
    for i, line in enumerate(lines):
        m = re.match(r"\s*(?:@(\w+)\.route|app\.add_url_rule)\(\s*['\"]([^'\"]*)['\"]\s*(?:,\s*methods\s*=\s*(\[[^\]]*\]))?", line)
        if not m:
            continue
        bp, path, methods = m.group(1), m.group(2), m.group(3)
        prefix = bp_prefix.get(bp, '') if bp else ''
        meths = re.findall(r"['\"](\w+)['\"]", methods) if methods else ['GET']
        # decorators directly above the route
        # in this codebase the guard sits BELOW the route decorator, above `def`
        auth = []
        j = i + 1
        while j < len(lines) and not re.match(r"\s*def ", lines[j]):
            for d in re.findall(r"@(\w+)", lines[j]):
                if d in ('require_auth', 'require_admin', 'require_super_admin', 'require_role',
                         'require_staff', 'admin_required', 'super_admin_required', 'auth_required'):
                    auth.append(d)
            j += 1
            if j - i > 6:
                break
        routes.append((meths, (prefix + path).replace('//', '/'), f"{os.path.relpath(f, REPO)}:{i+1}", auth))

routes = sorted({(tuple(r[0]), r[1], r[2], tuple(r[3])) for r in routes}, key=lambda r: r[1])

# --------------------------------------------------------------- frontend side
calls = []    # (http, path, file:line, note)
for f in glob.glob(os.path.join(FE, 'lib/liveApi.ts')):
    src = open(f).read()
    for i, line in enumerate(src.split('\n')):
        for m in re.finditer(r"apiClient\.(get|post|patch|delete|put)\(\s*[`'\"]([^`'\"]+)[`'\"]", line):
            calls.append((m.group(1).upper(), m.group(2), f"{os.path.relpath(f, REPO)}:{i+1}", ''))
for f in glob.glob(os.path.join(FE, '**/*.ts*'), recursive=True):
    src = open(f).read()
    for i, line in enumerate(src.split('\n')):
        for m in re.finditer(r"fetch\(\s*[`'\"](/api/[^`'\"]+)[`'\"]", line):
            calls.append(('(fetch)', m.group(1).replace('/api', ''), f"{os.path.relpath(f, REPO)}:{i+1}", 'relative /api'))
        for m in re.finditer(r"fetch\(\s*`([^`]*\$\{[^`]*)`", line):
            calls.append(('(fetch)', m.group(1), f"{os.path.relpath(f, REPO)}:{i+1}", 'relative /api'))

def norm(p):
    p = re.sub(r'\$\{[^}]*\}', ':p', p)
    p = re.sub(r'<[^>]+>', ':p', p)
    p = re.sub(r':\w+', ':p', p)
    p = p.split('?')[0].rstrip('/')
    return p

def route_regex(route):
    # escape, then turn Flask params (<name>, <int:name>) into a segment matcher
    out, i = '', 0
    for m in re.finditer(r"<[^>]+>", route):
        out += re.escape(route[i:m.start()]) + r"[^/]+"
        i = m.end()
    out += re.escape(route[i:])
    return re.compile('^' + out.rstrip('/') + '/?$')

route_regexes = []
for meths, path, loc, auth in routes:
    route_regexes.append((meths, route_regex(path), path, loc, auth))

rows_fe = []
for http, path, loc, note in calls:
    if http == '(fetch)' and 'BASE_URL' in path:
        continue  # the apiClient's own template, not a call site
    if http == '(fetch)':
        rows_fe.append((loc, http, path, '— (relative call, not via apiClient)', 'ORPHAN-TBC' if '/apps/' in path else 'check'))
        continue
    # apiClient calls are relative to API_BASE_URL (…/api) — Flask blueprints
    # are registered under /api, so compare against the prefixed path.
    path = '/api' + path if not path.startswith('/api') else path
    hit = [r for r in route_regexes if r[1].match(path) and http in r[0]]
    if hit:
        r = hit[0]
        rows_fe.append((loc, http, path, f"{r[3]}  (auth: {','.join(r[4]) or 'public'})", 'correct'))
    else:
        same_path = [r for r in route_regexes if r[1].match(path)]
        alt = [f"{'/'.join(r[0])} {r[3]}" for r in same_path]
        rows_fe.append((loc, http, path, '; '.join(alt) if alt else 'NO FLASK ROUTE',
                        'wrong method' if alt else '404 / orphaned'))

print(f"FLASK ROUTES: {len(routes)}")
print(f"FE CALLS: {len(calls)}")
print()
print("### UNMATCHED FE CALLS")
for r in rows_fe:
    if r[4] not in ('correct',):
        print(f"  {r[4]:14} {r[1]:7} {r[2][:60]:60} {r[0]}")
print()
print("### FE CALLS WITH WRONG METHOD ONLY")
for r in rows_fe:
    if r[4] == 'wrong method':
        print(f"  {r[1]:7} {r[2][:55]:55} available: {r[3]}  {r[0]}")

json.dump({'routes': [list(r) for r in routes], 'calls': [list(r) for r in rows_fe]}, open('/tmp/coverage.json', 'w'), indent=1)
