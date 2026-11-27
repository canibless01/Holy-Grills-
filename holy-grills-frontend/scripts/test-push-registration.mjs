/** Exercise actual v16 initialization, permission/registration and ready-gate boundaries. */
import { build } from 'esbuild';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { pathToFileURL } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const temp = await mkdtemp(join(tmpdir(), 'holy-push-v16-'));
try {
  const output = join(temp, 'onesignal.mjs');
  await build({
    entryPoints: [join(root, 'src', 'lib', 'onesignal.ts')], bundle: true, format: 'esm', platform: 'node', outfile: output,
    plugins: [{ name: 'controlled-dependencies', setup(builder) {
      builder.onResolve({ filter: /^@\// }, ({ path }) => {
        // The real origin guard is bundled, not stubbed: the alias behaviour is
        // part of what this test proves.
        if (path === '@/lib/canonicalOrigin') return { path: join(root, 'src', 'lib', 'canonicalOrigin.ts') };
        return { path, namespace: 'fixture' };
      });
      builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({ contents:
        path === '@/native/pushState' ? 'export const nativePushState={registered:false,permission:"default"};' :
        path === '@/native/platform' ? 'export const isNativeApp=()=>false;' :
        path === '@/native/push' ? 'export const nativePushReady=()=>{throw Error("Web must not call native push")};export const nativePushLogout=nativePushReady;export const nativePushPermission=nativePushReady;export const nativePushOptOut=nativePushReady;export const nativePushRegistered=nativePushReady;' :
        path.includes('app.config') ? 'export default {onesignal:{appId:\'fixture\'}};' :
        path.includes('liveApi') ? 'export const liveApi={auth:{deviceToken:async body=>globalThis.__register(body),removeDeviceToken:async body=>globalThis.__unregister(body)},notifications:{updatePreferences:async body=>globalThis.__prefs.push(body)}};' :
        'export const msg=(_key,fallback)=>fallback;' }));
    } }],
  });

  const eventSets = () => {
    const map = new Map();
    return { addEventListener: (event,fn) => { if (!map.has(event)) map.set(event,new Set()); map.get(event).add(fn); },
      removeEventListener: (event,fn) => map.get(event)?.delete(fn),
      emit: async (event,payload) => { for (const fn of map.get(event)||[]) await fn(payload); },
      size: event => map.get(event)?.size || 0 };
  };

  /**
   * A controllable stand-in for the v16 page SDK. Counters are per instance so a
   * fresh module (a fresh page load) can be exercised independently.
   */
  const makeSdk = () => {
    const counts = { init: 0, login: 0, permission: 0, logout: 0, optIn: 0, optOut: 0 };
    const permissions = eventSets(); const subscriptions = eventSets();
    const sub = { id: null, optedIn: false, ...subscriptions,
      optIn: async () => { counts.optIn++; },
      optOut: async () => { counts.optOut++; } };
    const sdk = {
      init: async (options) => { counts.init++; assert.equal(options.promptOptions.slidedown.prompts[0].autoPrompt, false); },
      login: async () => { counts.login++; },
      logout: async () => { counts.logout++; },
      Notifications: { ...permissions, requestPermission: async () => { counts.permission++; } },
      User: { PushSubscription: sub },
    };
    return { sdk, counts, permissions, subscriptions, sub };
  };

  const registrations = [];
  const removals = [];
  globalThis.__unregister = async body => removals.push(body);
  const prefs = [];
  let registrationError = null;
  globalThis.__prefs = prefs;
  globalThis.document = { querySelector: () => ({}) };
  globalThis.window = { location: { protocol: 'https:', hostname: 'holygrills.online', pathname: '/', search: '', hash: '',
    replace: (url) => { globalThis.__redirectedTo = url; } } };
  Object.defineProperty(globalThis, 'navigator', { value: { userAgent: 'controlled-v16' }, configurable: true });
  globalThis.Notification = { permission: 'default' };
  globalThis.__register = async (body) => { if (registrationError) throw registrationError; registrations.push(body); };

  // ── 1. Login-time initialization (unchanged behaviour) ──────────────────
  const first = makeSdk();
  globalThis.window.OneSignalDeferred = { push: (fn) => queueMicrotask(() => fn(first.sdk)) };
  const module = await import(pathToFileURL(output));
  await Promise.all([module.initOneSignal('fixture-user'), module.initOneSignal('fixture-user')]);
  assert.equal(first.counts.init, 1);
  assert.equal(first.counts.login, 1);
  assert.equal(first.counts.permission, 0, 'SDK setup never asks permission');

  let settled = false;
  const claim = module.requestPushPermission().then((v) => { settled = true; return v; });
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(settled, false);
  assert.equal(registrations.length, 0);
  Notification.permission = 'granted';
  await first.permissions.emit('permissionChange', true);
  assert.equal(settled, false, 'permission alone is not registration');
  first.sub.id = 'fixture-subscription';
  first.sub.optedIn = true;
  await first.subscriptions.emit('change', { current: { id: first.sub.id } });
  assert.equal(await claim, true);
  assert.ok(registrations.length >= 1);
  // POST /auth/device-token contract: { token, platform, device_model }.
  assert.ok(registrations.every((r) => r.token === 'fixture-subscription' && r.platform === 'web'));
  assert.ok(prefs.some((p) => p.push_enabled === true), 'the push preference is enabled server-side on success');
  assert.equal(first.permissions.size('permissionChange'), 0, 'temporary listener removed');
  assert.equal(first.subscriptions.size('change'), 1, 'only persistent SDK listener remains');

  registrationError = new Error('fixture registration unavailable');
  first.sub.id = 'failed-subscription';
  await assert.rejects(module.requestPushPermission(), /registration unavailable/);
  registrationError = null;

  Notification.permission = 'denied';
  assert.equal(await module.requestPushPermission(), false);
  await module.optOutOneSignal();
  assert.equal(first.counts.optOut, 1);
  await module.logoutOneSignal();
  assert.equal(first.counts.logout, 1);
  assert.equal(await module.requestPushPermission(), false, 'logged-out denied browser stays denied');

  // ── 2. Ready gate: the Enable tap waits for a slow SDK instead of racing it ──
  const slow = makeSdk();
  globalThis.window.OneSignalDeferred = { push: (fn) => setTimeout(() => fn(slow.sdk), 40) };
  const slowModule = await import(`${pathToFileURL(output).href}?slow`);
  const ready = slowModule.ensurePushReady('slow-user', 5000);
  await new Promise((resolve) => setTimeout(resolve, 5));
  assert.equal(slow.counts.init, 0, 'SDK has not loaded yet — the tap must be waiting, not failing');
  await ready;
  assert.equal(slow.counts.init, 1, 'ready resolved after initialization');
  assert.equal(slow.counts.login, 1, 'the signed-in user is identified before the prompt');
  assert.equal(slow.counts.permission, 0, 'waiting for readiness never asks permission by itself');

  // Permission request afterwards is the normal path, not a "still loading" error.
  Notification.permission = 'granted';
  const lateClaim = slowModule.requestPushPermission();
  slow.sub.id = 'slow-subscription';
  slow.sub.optedIn = true;
  await slow.subscriptions.emit('change', { current: { id: slow.sub.id } });
  assert.equal(await lateClaim, true);

  // ── 3. A genuinely unavailable SDK reports a real, retryable reason ─────
  // The SDK's own init bound is 15s; shrink long timers for this phase so the
  // suite proves the bounded wait without waiting it out.
  const realSetTimeout = globalThis.setTimeout;
  globalThis.setTimeout = (callback, ms, ...args) => realSetTimeout(callback, ms >= 1000 ? 5 : ms, ...args);
  try {
    const stalled = makeSdk();
    globalThis.window.OneSignalDeferred = [];
    const stalledModule = await import(`${pathToFileURL(output).href}?stalled`);
    await assert.rejects(stalledModule.ensurePushReady('stalled-user', 30), /couldn’t load/i);
    await assert.rejects(stalledModule.requestPushPermission(), /still loading/);

    // ── 4. Guests register anonymously, then login adopts that subscription ──
    const guest = makeSdk();
    globalThis.window.OneSignalDeferred = { push: (fn) => queueMicrotask(() => fn(guest.sdk)) };
    const guestModule = await import(`${pathToFileURL(output).href}?guest`);
    const beforeGuest = registrations.length, beforePrefs = prefs.length;
    Notification.permission = 'default';
    await guestModule.ensurePushReady(null, 30);
    assert.equal(guest.counts.init, 1); assert.equal(guest.counts.login, 0);
    assert.equal(guest.counts.permission, 0, 'warming an anonymous SDK never prompts');
    guest.sub.id = 'guest-subscription';
    guest.sdk.Notifications.requestPermission = async () => {
      guest.counts.permission++; Notification.permission = 'granted'; guest.sub.optedIn = true;
    };
    assert.equal(await guestModule.requestPushPermission(), true);
    assert.equal(guestModule.isPushRegistered(), true);
    assert.equal(guest.counts.permission, 1);
    assert.equal(registrations.length, beforeGuest, 'guest never calls account device-token endpoint');
    assert.equal(prefs.length, beforePrefs, 'guest never changes account preferences');
    await guestModule.initOneSignal('new-member');
    assert.equal(guest.counts.login, 1);
    assert.equal(registrations.at(-1).token, 'guest-subscription');
    assert.equal(await guestModule.requestPushPermission(), true);
    assert.equal(guest.counts.permission, 1, 'login does not ask native permission again');
    assert.equal(prefs.length, beforePrefs + 1);
    let releaseLogout;
    guest.sdk.logout = () => new Promise(resolve => { releaseLogout = resolve; });
    const logout = guestModule.logoutOneSignal();
    let guestReady = false;
    const waitGuest = guestModule.ensurePushReady(null, 30).then(() => { guestReady = true; });
    await new Promise(resolve => realSetTimeout(resolve, 0));
    assert.equal(guestReady, false, 'anonymous enable waits for old identity logout');
    releaseLogout(); await logout; await waitGuest;
    assert.equal(guestModule.isPushRegistered(), true);

    // Disabled/permission-only IDs must not be advertised as reachable devices.
    const lifecycle = makeSdk();
    lifecycle.sub.id = 'disabled-device';
    globalThis.window.OneSignalDeferred = { push: fn => queueMicrotask(() => fn(lifecycle.sdk)) };
    Notification.permission = 'granted';
    const lifecycleModule = await import(`${pathToFileURL(output).href}?device-lifecycle`);
    const registrationsBefore = registrations.length;
    await lifecycleModule.initOneSignal('lifecycle-member');
    assert.equal(registrations.length, registrationsBefore, 'an ID without opt-in cannot be registered');
    assert.equal(removals.at(-1).token, 'disabled-device');
    assert.equal(lifecycleModule.isPushRegistered(), false);
    lifecycle.sub.optedIn = true;
    await lifecycle.subscriptions.emit('change', { current: { id: lifecycle.sub.id } });
    assert.equal(lifecycleModule.isPushRegistered(), true);
    lifecycle.sub.optedIn = false;
    await lifecycle.subscriptions.emit('change', { current: { id: lifecycle.sub.id } });
    assert.equal(lifecycleModule.isPushRegistered(), false);
    assert.equal(removals.at(-1).token, 'disabled-device');
    assert.ok(removals.every(body => Object.keys(body).join() === 'token'), 'revocation never selects an account');

    // A delayed POST cannot land after the opt-out DELETE and leave stale eligibility.
    let releaseRegistration;
    const ordinaryRegister = globalThis.__register;
    globalThis.__register = async body => {
      if (body.token === 'pending-device') await new Promise(resolve => { releaseRegistration = resolve; });
      await ordinaryRegister(body);
    };
    lifecycle.sub.id = 'pending-device'; lifecycle.sub.optedIn = true;
    const inFlight = lifecycle.subscriptions.emit('change', { current: { id: lifecycle.sub.id } });
    await new Promise(resolve => realSetTimeout(resolve, 0));
    assert.equal(typeof releaseRegistration, 'function');
    lifecycle.sub.optedIn = false;
    const optedOut = lifecycle.subscriptions.emit('change', { current: { id: lifecycle.sub.id } });
    releaseRegistration(); await inFlight; await optedOut;
    assert.equal(removals.at(-1).token, 'pending-device');
    assert.equal(lifecycleModule.isPushRegistered(), false);
    globalThis.__register = ordinaryRegister;

    // Subscription rotation removes only its known previous ID, then registers the new one.
    lifecycle.sub.id = 'replacement-device'; lifecycle.sub.optedIn = true;
    await lifecycle.subscriptions.emit('change', { previous: { id: 'pending-device' }, current: { id: lifecycle.sub.id } });
    assert.equal(registrations.at(-1).token, 'replacement-device');
    assert.equal(removals.at(-1).token, 'pending-device');
    assert.equal(lifecycleModule.isPushRegistered(), true);

    // ── 5. www alias: never initialize the SDK on the wrong origin ──────────
    globalThis.__redirectedTo = null;
    const alias = makeSdk();
    globalThis.window.OneSignalDeferred = { push: (fn) => queueMicrotask(() => fn(alias.sdk)) };
    globalThis.window.location = {
      protocol: 'https:', hostname: 'www.holygrills.online', pathname: '/notification-preferences',
      search: '?tab=push', hash: '', replace: (url) => { globalThis.__redirectedTo = url; },
    };
    const aliasModule = await import(`${pathToFileURL(output).href}?alias`);
    await aliasModule.initOneSignal('alias-user');
    assert.equal(alias.counts.init, 0, 'no SDK init on the alias origin');
    assert.equal(alias.counts.login, 0, 'no identity call on the alias origin');
    assert.equal(globalThis.__redirectedTo, 'https://holygrills.online/notification-preferences?tab=push&hg_origin=bounced',
      'the visitor is moved to the configured origin with the URL intact');
    await assert.rejects(aliasModule.ensurePushReady('alias-user', 30), /only available on https:\/\/holygrills\.online/);

    // ── 6. Bounced back by the host: never init, never promise a redirect ──
    // This is the 29 Oct infinite-reload shape: the host keeps returning the
    // document to www. The guard stands down, the app renders, and push says
    // where it actually works instead of redirecting again.
    globalThis.__redirectedTo = null;
    const bounced = makeSdk();
    globalThis.window.OneSignalDeferred = { push: (fn) => queueMicrotask(() => fn(bounced.sdk)) };
    globalThis.window.location = {
      protocol: 'https:', hostname: 'www.holygrills.online', pathname: '/notification-preferences',
      search: '?tab=push&hg_origin=bounced', hash: '', replace: (url) => { globalThis.__redirectedTo = url; },
    };
    const bouncedModule = await import(`${pathToFileURL(output).href}?bounced`);
    await bouncedModule.initOneSignal('bounced-user');
    assert.equal(bounced.counts.init, 0, 'still no SDK init on a bounced alias document');
    assert.equal(globalThis.__redirectedTo, null, 'a bounced document is never redirected again');
    await assert.rejects(bouncedModule.ensurePushReady('bounced-user', 30),
      /Push only works on https:\/\/holygrills\.online/);
  } finally { globalThis.setTimeout = realSetTimeout; }

  console.log('PASS v16 single-flight, verified identity, no automatic permission, permission-only refusal, '
    + 'backend registration failure, denied permission, cleanup, v16 opt-out, logout, bounded stalled SDK, '
    + 'disabled-device cleanup, serialised opt-out/write races, owned token rotation, ready gate before the prompt, anonymous guest registration without private writes, login adoption, serialized guest logout, no SDK init on the www alias, and no redirect loop when the host bounces back');
} finally {
  await rm(temp, { recursive: true, force: true });
}
