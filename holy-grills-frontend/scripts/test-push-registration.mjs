/** Exercise the actual OneSignal module against controlled SDK outcomes. */
import { build } from 'esbuild';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const temp = await mkdtemp(join(tmpdir(), 'holy-push-'));
const output = join(temp, 'onesignal.mjs');
try {
  await build({ entryPoints: ['src/lib/onesignal.ts'], bundle: true, format: 'esm', platform: 'node', outfile: output,
    plugins: [{ name: 'controlled-dependencies', setup(builder) {
      builder.onResolve({ filter: /^@\// }, ({ path }) => ({ path, namespace: 'fixture' }));
      builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({ contents:
        path.includes('app.config') ? "export default {onesignal:{appId:'fixture'}};" :
        path.includes('liveApi') ? 'export const liveApi={auth:{deviceToken:async body=>globalThis.__register(body)}};' :
        'export const msg=(_key,fallback)=>fallback;' }));
    } }],
  });
  let enabled = false, permission = 'default', player = null, registrations = [], registrationError = null;
  globalThis.__register = async body => { if (registrationError) throw registrationError; registrations.push(body); };
  globalThis.document = { querySelector: () => ({}) };
  Object.defineProperty(globalThis, 'navigator', {value: {userAgent: 'controlled-fixture'}, configurable: true});
  globalThis.Notification = { permission: 'default' };
  const events = new Map();
  globalThis.window = { OneSignal: {
    push: fn => fn(), init: () => {}, setExternalUserId: () => {},
    getUserId: async () => player, getNotificationPermission: async () => permission,
    isPushNotificationsEnabled: async () => enabled, showSlidedownPrompt: async () => {},
    on: (event, fn) => { if (!events.has(event)) events.set(event, new Set()); events.get(event).add(fn); },
    off: (event, fn) => events.get(event)?.delete(fn),
  } };
  const module = await import(pathToFileURL(output));
  await module.initOneSignal('fixture-user');
  const tick = () => new Promise(resolve => setTimeout(resolve, 15));
  const emit = async () => { for (const fn of events.get('subscriptionChange') || []) await fn(); };
  let settled = false;
  const claim = module.requestPushPermission().then(value => { settled = true; return value; });
  await tick(); assert.equal(settled, false, 'opening a prompt cannot claim push');
  assert.equal(registrations.length, 0);
  permission = 'granted'; await emit(); assert.equal(settled, false, 'permission alone is insufficient');
  enabled = true; player = 'fixture-player'; await emit();
  assert.equal(await claim, true); assert.equal(registrations.length, 1);
  assert.equal(registrations[0].player_id, 'fixture-player');
  assert.equal(events.get('notificationPermissionChange').size, 0, 'listeners cleaned up');
  registrationError = new Error('fixture registration unavailable');
  await assert.rejects(module.requestPushPermission(), /registration unavailable/);
  registrationError = null; Notification.permission = 'denied';
  assert.equal(await module.requestPushPermission(), false);
  assert.equal(registrations.length, 1, 'denied permission cannot register or claim');
  console.log('PASS: prompt-only, permission-only, granted+subscribed, failed registration, denied permission, cleanup');
} finally { await rm(temp, { recursive: true, force: true }); }
