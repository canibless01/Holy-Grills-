import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { rmSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const out = join(root, 'node_modules', '.cache-csv-cell.mjs');
execFileSync(join(root, 'node_modules', '.bin', 'esbuild'), [join(root, 'src/lib/csvCell.ts'), '--format=esm', `--outfile=${out}`]);
try {
  const { csvCell } = await import(out);
  for (const input of ['=HYPERLINK("https://example.invalid")', '+SUM(1,2)', '-1+2', '@SUM(1)', '\t=1', '\uFEFF=1']) {
    assert.ok(csvCell(input).startsWith("'"));
  }
  assert.equal(csvCell('A "quoted" name'), 'A ""quoted"" name');
  assert.equal(csvCell(0), '0');
  assert.equal(csvCell(null), '');
  assert.equal(csvCell('ordinary, value'), 'ordinary, value');
  console.log('CSV export formula and quoting checks passed');
} finally { rmSync(out, { force: true }); }
