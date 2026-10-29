import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const temp = await mkdtemp(join(tmpdir(), 'hg-worker-lifecycle-'));
try {
  const file = join(temp, 'lifecycle.mjs');
  await build({ entryPoints: ['src/lib/serviceWorkerLifecycle.ts'], bundle: true, format: 'esm', outfile: file });
  globalThis.window = { location: { origin: 'https://holygrills.online' } };
  const { registerAppServiceWorker, watchServiceWorkerController } = await import(pathToFileURL(file));
  const plain = 'https://holygrills.online/service-worker.js';
  const sdk = `${plain}?appId=fixture&sdkVersion=160610`;
  let listener; const registrations = []; let reloads = 0;
  const workers = {
    controller: null,
    getRegistration: async () => ({ active: workers.controller }),
    register: async url => { registrations.push(url); },
    addEventListener: (_name, fn) => { listener = fn; },
    removeEventListener: () => { listener = null; },
  };
  const dispose = watchServiceWorkerController(workers, () => { reloads++; });
  await registerAppServiceWorker(workers);
  assert.deepEqual(registrations, ['/service-worker.js']);
  workers.controller = { scriptURL: plain }; listener();
  assert.equal(reloads, 0, 'first install preserves the open page');
  workers.controller = { scriptURL: sdk }; listener();
  assert.equal(reloads, 0, 'SDK query change preserves the form and storefront cache');
  await registerAppServiceWorker(workers);
  assert.equal(registrations.at(-1), sdk, 'returning app boot retains the shared SDK registration');
  workers.controller = { scriptURL: `${sdk}&revision=2` }; listener();
  assert.equal(reloads, 0, 'SDK version/query updates also preserve the document');
  listener(); listener();
  assert.equal(reloads, 1, 'a new worker at the unchanged script URL still reloads exactly once');
  dispose(); assert.equal(listener, null);
  console.log('PASS shared PWA/OneSignal worker: first claim, SDK query changes, returning registration and real updates');
} finally { await rm(temp, { recursive: true, force: true }); }
