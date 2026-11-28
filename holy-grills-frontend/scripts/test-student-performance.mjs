import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const dir = await mkdtemp(join(tmpdir(), 'hg-performance-'));
try {
  const file = join(dir, 'test.mjs');
  await build({ stdin: { contents: `export * from './src/lib/apiClient'; export * from './src/lib/featureConfig'; export * from './src/lib/menuImages';`, resolveDir: process.cwd() },
    bundle: true, format: 'esm', platform: 'node', outfile: file,
    define: { 'import.meta.env.VITE_API_BASE_URL': '"https://test.invalid/api"' } });
  const storage = () => { const map = new Map(); return { getItem: key => map.get(key) ?? null, setItem: (key, value) => map.set(key, value), removeItem: key => map.delete(key) }; };
  globalThis.window = { localStorage: storage(), sessionStorage: storage() };
  const lib = await import(pathToFileURL(file));
  const original = 'https://res.cloudinary.com/demo/image/upload/v123/menu/food.jpg';
  assert.match(lib.menuImage(original), /f_auto,q_auto,c_limit,w_480\/v123/);
  assert.equal(lib.menuImage('https://example.com/food.jpg'), 'https://example.com/food.jpg');
  assert.equal(lib.menuImage('https://res.cloudinary.com/demo/image/upload/s--signature--/v123/food.jpg'), 'https://res.cloudinary.com/demo/image/upload/s--signature--/v123/food.jpg');
  assert.equal(lib.menuImage('https://res.cloudinary.com/demo/image/upload/w_600/v123/food.jpg'), 'https://res.cloudinary.com/demo/image/upload/w_600/v123/food.jpg');
  assert.equal(lib.menuImageSet(original).split(', https').length, 3);
  const calls = [];
  globalThis.fetch = (url, options) => new Promise(resolve => calls.push({ url, options, resolve }));
  const finish = (call, data, status = 200) => call.resolve(new Response(JSON.stringify(data), { status, headers: { 'content-type': 'application/json' } }));
  lib.setTokens('student-token', 'refresh'); window.localStorage.setItem('hg_user_role', 'student');
  const menu = lib.apiClient.get('/menu/items', { available_only: 'true' });
  assert.equal(calls.at(-1).options.headers.Authorization, undefined); finish(calls.at(-1), {}); await menu;
  const management = lib.apiClient.get('/menu/items', { available_only: 'false' });
  assert.equal(calls.at(-1).options.headers.Authorization, 'Bearer student-token'); finish(calls.at(-1), {}); await management;
  const secret = lib.apiClient.get('/menu/items', { available_only: 'true', include_secret: '1' });
  assert.equal(calls.at(-1).options.headers.Authorization, 'Bearer student-token'); finish(calls.at(-1), {}); await secret;
  const initial = lib.loadSystemSettings(); finish(calls.at(-1), { delivery_fee: 500 }); await initial;
  assert.equal(lib.getSetting('delivery_fee'), 500);
  const stale = lib.loadSystemSettings(); const staleCall = calls.at(-1);
  assert.equal(lib.getSetting('delivery_fee'), 500, 'no temporary default while refreshing');
  const write = lib.apiClient.patch('/admin/settings/delivery_fee', { value: 900 }); finish(calls.at(-1), {}); await write;
  const refreshed = lib.loadSystemSettings(); const currentCall = calls.at(-1);
  assert.notEqual(currentCall, staleCall, 'post-save settings must not join pre-save read');
  finish(currentCall, { delivery_fee: 900 }); await refreshed;
  finish(staleCall, { delivery_fee: 100 }); await stale;
  assert.equal(lib.getSetting('delivery_fee'), 900);
  const oldWallet = lib.apiClient.get('/wallet'); const oldWalletCall = calls.at(-1);
  const paid = lib.apiClient.post('/wallet/fund/card/verify', { reference: 'synthetic' }); finish(calls.at(-1), {}); await paid;
  const freshWallet = lib.apiClient.get('/wallet'); const freshWalletCall = calls.at(-1);
  assert.notEqual(freshWalletCall, oldWalletCall, 'confirmed funding must not join a pre-funding balance read');
  finish(freshWalletCall, { balance: 900 }); assert.equal((await freshWallet).balance, 900);
  finish(oldWalletCall, { balance: 100 }); await oldWallet;
  lib.setTokens('admin-token', 'refresh'); window.localStorage.setItem('hg_user_role', 'super_admin'); window.localStorage.setItem('hg_admin_scope_all', '1');
  const before = calls.length; const admin = lib.loadSystemSettings();
  assert.equal(calls.length, before + 2, 'public and private settings start in parallel');
  const privileged = calls.findLast(call => call.url.endsWith('/admin/settings'));
  finish(calls[before], { delivery_fee: 800 });
  finish(privileged, { settings: [{ key: 'private_value', value: 'private', campus_id: null }] }); await admin;
  assert.equal(lib.getSetting('private_value'), 'private');
  lib.clearTokens(); assert.equal(lib.getSetting('private_value', 'hidden'), 'hidden');
  console.log('PASS responsive images; public/management auth split; atomic parallel configuration; post-save and account-switch race safety');
} finally { await rm(dir, { recursive: true, force: true }); }
