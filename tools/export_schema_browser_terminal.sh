#!/usr/bin/env bash
# Run in your own browser terminal; reads the source and writes private local files only.
set -euo pipefail
umask 077
export_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export_output="${1:-$export_root/work/database-schema-$(date -u +%Y%m%d-%H%M%S)}"
export_python="${HG_SCHEMA_EXPORT_PYTHON:-$export_root/work/schema-export-venv/bin/python}"

if [[ ! -x "$export_python" ]]; then
  python3 -m venv "$export_root/work/schema-export-venv"
  "$export_python" -m pip install --disable-pip-version-check 'psycopg2-binary==2.9.12'
fi
if ! command -v pg_dump >/dev/null 2>&1 && ! command -v docker >/dev/null 2>&1; then
  printf '%s\n' 'PostgreSQL 17+ client tools or Docker are required.' >&2
  exit 1
fi
if [[ -z "${SOURCE_DATABASE_URL:-}" ]]; then
  printf '%s\n' 'Paste the Supabase SESSION POOLER connection URL below. Input is hidden.'
  IFS= read -r -s -p 'Source URL: ' SOURCE_DATABASE_URL </dev/tty
  printf '\n'
fi
export SOURCE_DATABASE_URL
trap 'unset SOURCE_DATABASE_URL' EXIT
"$export_python" "$export_root/tools/export_database_architecture.py" --output "$export_output"
unset SOURCE_DATABASE_URL

export_archive="${export_output}.zip"
"$export_python" - "$export_output" "$export_archive" <<'PY'
import os,sys,zipfile
from pathlib import Path
source=Path(sys.argv[1]);target=Path(sys.argv[2])
assert (source/'manifest.json').is_file(),'Export did not complete; no archive created.'
with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as archive:
    for file in sorted(source.rglob('*')):
        if file.is_file():archive.write(file,str(file.relative_to(source)))
os.chmod(target,0o600)
PY
printf 'Schema-only export complete: %s\n' "$export_archive"
if command -v cloudshell >/dev/null 2>&1; then
  cloudshell download "$export_archive"
else
  printf '%s\n' 'Download this ZIP using your terminal/file browser. Keep it private.'
fi
