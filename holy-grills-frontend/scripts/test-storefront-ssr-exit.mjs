// A rendered page is not a completed build if a query-cache timer keeps Node
// alive. Exercise the real SSR bundle in a child that must exit on its own.
import { execFileSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const entry = pathToFileURL(join(root, 'dist-ssr/entry-server.js')).href;
const program = `const { render } = await import(${JSON.stringify(entry)});
const html = await render('/');
if (html.length < 1000) throw new Error('Home SSR did not finish');
console.log('Home SSR rendered and exited without a cache timer');`;
const output = execFileSync(process.execPath, ['--input-type=module', '-e', program], {
  timeout: 15000, encoding: 'utf8',
});
console.log(output.trim());
