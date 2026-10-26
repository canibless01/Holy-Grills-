/** Exercise actual v16 initialization and permission/registration boundaries. */
import { build } from 'esbuild';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
const temp = await mkdtemp(join(tmpdir(), 'holy-push-v16-'));
try {
  const output = join(temp, 'onesignal.mjs');
  await build({ entryPoints: ['src/lib/onesignal.ts'], bundle: true, format: 'esm', platform: 'node', outfile: output,
    plugins: [{ name: 'controlled-dependencies', setup(builder) {
      builder.onResolve({ filter: /^@\// }, ({ path }) => ({ path, namespace: 'fixture' }));
      builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({ contents:
        path.includes('app.config') ? "export default {onesignal:{appId:'fixture'}};" :
        path.includes('liveApi') ? 'export const liveApi={auth:{deviceToken:async body=>globalThis.__register(body)}};' :
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
  let initializeCalls=0, loginCalls=0, permissionCalls=0, logoutCalls=0, optOutCalls=0, registrationError=null;
  const registrations=[];const permissions=eventSets(),subscriptions=eventSets();
  const sub={id:null,optedIn:false,...subscriptions,optOut:async()=>{optOutCalls++;}};
  const sdk={init:async options=>{initializeCalls++;assert.equal(options.promptOptions.slidedown.prompts[0].autoPrompt,false);},login:async()=>{loginCalls++;},logout:async()=>{logoutCalls++;},Notifications:{...permissions,requestPermission:async()=>{permissionCalls++;}},User:{PushSubscription:sub}};
  globalThis.document={querySelector:()=>({})};
  globalThis.window={OneSignalDeferred:{push:fn=>queueMicrotask(()=>fn(sdk))}};
  Object.defineProperty(globalThis,'navigator',{value:{userAgent:'controlled-v16'},configurable:true});
  globalThis.Notification={permission:'default'};
  globalThis.__register=async body=>{if(registrationError)throw registrationError;registrations.push(body);};
  const module=await import(pathToFileURL(output));
  await Promise.all([module.initOneSignal('fixture-user'),module.initOneSignal('fixture-user')]);
  assert.equal(initializeCalls,1);assert.equal(loginCalls,1);assert.equal(permissionCalls,0,'SDK setup never asks permission');
  let settled=false;const claim=module.requestPushPermission().then(v=>{settled=true;return v;});
  await new Promise(resolve=>setTimeout(resolve,10));assert.equal(settled,false);assert.equal(registrations.length,0);
  Notification.permission='granted';await permissions.emit('permissionChange',true);assert.equal(settled,false,'permission alone is not registration');
  sub.id='fixture-subscription';sub.optedIn=true;await subscriptions.emit('change',{current:{id:sub.id}});assert.equal(await claim,true);assert.ok(registrations.length>=1);assert.ok(registrations.every(r=>r.player_id==='fixture-subscription'));assert.equal(permissions.size('permissionChange'),0,'temporary listener removed');assert.equal(subscriptions.size('change'),1,'only persistent SDK listener remains');
  registrationError=new Error('fixture registration unavailable');sub.id='failed-subscription';await assert.rejects(module.requestPushPermission(),/registration unavailable/);registrationError=null;
  Notification.permission='denied';assert.equal(await module.requestPushPermission(),false);
  await module.optOutOneSignal();assert.equal(optOutCalls,1);await module.logoutOneSignal();assert.equal(logoutCalls,1);await assert.rejects(module.requestPushPermission(),/still loading/);
  // Deferred SDK never fires: initialization must settle rather than hanging forever.
  window.OneSignalDeferred=[];const originalTimeout=globalThis.setTimeout;
  globalThis.setTimeout=(callback,ms,...args)=>originalTimeout(callback,ms===15000?1:ms,...args);
  try { const stalled=await import(pathToFileURL(output)+'?stalled');await stalled.initOneSignal('fixture-user');await assert.rejects(stalled.requestPushPermission(),/still loading/); }
  finally { globalThis.setTimeout=originalTimeout; }
  console.log('PASS v16 single-flight, verified identity, no automatic permission, permission-only refusal, backend registration failure, denied permission, cleanup, v16 opt-out, logout and bounded stalled SDK');
} finally { await rm(temp,{recursive:true,force:true}); }
