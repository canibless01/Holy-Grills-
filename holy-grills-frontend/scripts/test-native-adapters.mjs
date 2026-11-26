import {build} from 'esbuild';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const temp=await mkdtemp(join(tmpdir(),'hg-native-'));
const root=process.cwd();
try{
 const entry=join(temp,'entry.ts');
 await writeFile(entry,['secureSession','navigation','payments','apiFetch','push','devicePlatform','releaseManifest'].map(name=>`export * from ${JSON.stringify(resolve('src/native/'+name+'.ts'))};`).join('\n')+`\nexport * from ${JSON.stringify(resolve('src/lib/storage.ts'))};`);
 const output=join(temp,'test.mjs');
 await build({entryPoints:[entry],bundle:true,platform:'node',format:'esm',outfile:output,plugins:[{name:'native-boundaries',setup(b){
  b.onResolve({filter:/^@capacitor\/|^@onesignal\//},({path})=>({path,namespace:'fixture'}));
  b.onResolve({filter:/^@\//},({path})=>['@/config/app.config','@/lib/liveApi'].includes(path)?{path,namespace:'fixture'}:{path:resolve('src',path.slice(2))+'.ts'});
  b.onLoad({filter:/.*/,namespace:'fixture'},({path})=>({contents:
   path==='@capacitor/core'?`export const Capacitor={isNativePlatform:()=>globalThis.__native};export const registerPlugin=()=>globalThis.__vault;export const CapacitorHttp={request:options=>globalThis.__http(options)};`:
   path==='@capacitor/browser'?`export const Browser={open:options=>globalThis.__browser.push(options)};`:
   path==='@onesignal/capacitor-plugin'?`export default globalThis.__sdk;`:
   path==='@/config/app.config'?`export default {domain:'https://holygrills.online',onesignal:{appId:'471bd695-2342-4521-aa0f-8c93d7ce805f'}};`:
   `export const liveApi={auth:{deviceToken:async body=>{globalThis.__registered.push({...body,user:globalThis.__sdkUser});await Promise.resolve()},removeDeviceToken:async body=>globalThis.__removed.push(body)},notifications:{updatePreferences:async body=>globalThis.__prefs.push(body)}};`
  }));
 }}]});
 const store=()=>{const map=new Map();return{getItem:k=>map.get(k)??null,setItem:(k,v)=>map.set(k,String(v)),removeItem:k=>map.delete(k),clear:()=>map.clear()}};
 globalThis.localStorage=store();globalThis.sessionStorage=store();globalThis.window={localStorage,sessionStorage,location:{origin:'https://localhost',assign:url=>globalThis.__assigned=url},dispatchEvent:()=>{}};
 globalThis.__native=true;globalThis.__browser=[];let saved={access:'access-A',refresh:'refresh-A'},writes=[];
 globalThis.__vault={load:async()=>saved,save:async value=>{await new Promise(r=>setTimeout(r,3));saved={...value};writes.push(saved)},clear:async()=>{saved={};writes.push({})}};
 globalThis.__registered=[];globalThis.__removed=[];globalThis.__prefs=[];
 const events=new Map();let allowed=false,opted=false;let logins=[];let loginAResolve;let loginAStarted;
 const aStarted=new Promise(r=>loginAStarted=r);const holdA=new Promise(r=>loginAResolve=r);
 globalThis.__sdk={initialize:async()=>{},login:async user=>{logins.push(user);if(user==='A'){loginAStarted();await holdA;}globalThis.__sdkUser=user},logout:async()=>{globalThis.__sdkUser=null},
  Notifications:{hasPermission:async()=>allowed,canRequestPermission:async()=>!allowed,requestPermission:async()=>{allowed=true;return true},addEventListener:(name,fn)=>events.set(name,fn),clearAll:async()=>{}},
  User:{getExternalId:async()=>globalThis.__sdkUser||null,pushSubscription:{getIdAsync:async()=>'subscription-android',getOptedInAsync:async()=>opted,addEventListener:(name,fn)=>events.set('subscription',fn),optIn:async()=>{opted=true;events.get('subscription')?.()},optOut:async()=>{opted=false;events.get('subscription')?.()}}},InAppMessages:{setPaused:()=>{}}};
 const m=await import(pathToFileURL(output));
 assert.equal(m.mobilePlatform({userAgent:'Mozilla Android Chrome'}),'android');assert.equal(m.mobilePlatform({userAgent:'iPhone Safari'}),'ios');assert.equal(m.mobilePlatform({userAgent:'Macintosh',maxTouchPoints:5}),'ios');assert.equal(m.mobilePlatform({userAgent:'Macintosh',maxTouchPoints:0}),'other');
 const release={available:true,version:'1.0.0',versionCode:1,url:'https://github.com/canibless01/Holy-Grills-/releases/download/v1/Holy-Grills.apk',sha256:'a'.repeat(64)};
 assert.ok(m.validateAndroidRelease(release));assert.equal(m.validateAndroidRelease({...release,url:'https://evil.test/file.apk'}),null);assert.equal(m.validateAndroidRelease({...release,available:false}),null);assert.equal(m.validateAndroidRelease({...release,sha256:'invalid'}),null);
 console.log('PASS lightweight Android/iPhone/iPad/desktop detection and validated release manifest; no fingerprint or network lookup');
 localStorage.setItem('hg_access_token','UNPROTECTED');await m.restoreNativeSession();
 assert.equal(localStorage.getItem('hg_access_token'),null);assert.equal(m.localStore.getItem('hg_access_token'),'access-A');
 m.localStore.removeItem('hg_access_token');m.localStore.removeItem('hg_refresh_token');m.sessionStore.removeItem('hg_access_token');m.sessionStore.removeItem('hg_refresh_token');
 m.localStore.setItem('hg_access_token','access-B');m.localStore.setItem('hg_refresh_token','refresh-B');await m.flushNativeSession();
 assert.deepEqual(saved,{access:'access-B',refresh:'refresh-B'});assert.equal(localStorage.getItem('hg_access_token'),null);
 m.localStore.removeItem('hg_access_token');m.localStore.removeItem('hg_refresh_token');await m.flushNativeSession();assert.deepEqual(saved,{});
 localStorage.setItem('hg_remember','0');m.sessionStore.setItem('hg_access_token','session-only');await m.flushNativeSession();assert.deepEqual(saved,{});assert.equal(m.sessionStore.getItem('hg_access_token'),'session-only');
 console.log('PASS vault bootstrap, no plaintext JWTs, atomic token rotation, serialized logout and non-remembered sessions');
 for(const input of ['https://evil.test/orders/1','javascript:alert(1)','//evil.test','https://holygrills.online.evil.test/orders','https://holygrills.online/admin','https://u:p@holygrills.online/orders','holygrills://evil/orders'])assert.equal(m.nativeRoute(input),null,input);
 assert.equal(m.nativeRoute('https://holygrills.online/track-orders?order_number=X&claim_token=secret'),'/track-orders?order_number=X&claim_token=secret');
 assert.equal(m.nativeRoute('holygrills://app/orders/1?payment_return=1'),'/orders/1?payment_return=1');
 let route,verificationReturn;m.deliverNativeRoute('https://holygrills.online/orders/2');m.listenNativeRoutes((path,verify)=>{route=path;verificationReturn=verify});assert.equal(route,'/orders/2');
 await m.launchPayment('https://checkout.paystack.com/token','/orders/3?payment_return=1');assert.equal(__browser.length,1);assert.equal(m.resumeNativePayment(),true);assert.equal(route,'/orders/3?payment_return=1');assert.equal(verificationReturn,true);assert.equal(m.resumeNativePayment(),false);
 await assert.rejects(()=>m.launchPayment('https://evil.test/pay','/orders/3'));
 globalThis.__native=false;await m.launchPayment('https://checkout.paystack.com/web','/wallet');assert.equal(__assigned,'https://checkout.paystack.com/web');globalThis.__native=true;
 assert.equal(m.paymentCallback('/wallet'),'https://holygrills.online/wallet');console.log('PASS trusted cold/warm deep links, secret-query preservation, external URL rejection and native/web payment-return separation');
 let http;globalThis.__http=async request=>{http=request;return{status:200,data:{ok:true},headers:{'Content-Type':'application/json'}}};
 const res=await m.apiFetch('https://holygrills-production.up.railway.app/api/test',{method:'POST',headers:{Authorization:'Bearer private-token','Content-Type':'application/json'},body:'{"value":2}'});assert.deepEqual(await res.json(),{ok:true});assert.deepEqual(http.data,{value:2});assert.equal(http.headers.authorization,'Bearer private-token');
 await assert.rejects(()=>m.apiFetch('http://insecure.test/api'));const controller=new AbortController();controller.abort();await assert.rejects(()=>m.apiFetch('https://holygrills.online/api',{signal:controller.signal}));console.log('PASS existing JSON/bearer API over native HTTPS, no insecure URLs and aborted-request rejection');
 globalThis.__sdkUser='persisted-previous-account';await m.nativePushReady(null);assert.equal(__sdkUser,null);
 const a=m.nativePushReady('A');await aStarted;const logout=m.nativePushLogout();const b=m.nativePushReady('B');loginAResolve();await Promise.all([a,logout,b]);assert.deepEqual(logins,['A','B']);assert.equal(__registered.length,0);assert.equal(__sdkUser,'B');
 assert.equal(await m.nativePushPermission(),true);assert.equal(__registered.length,1);assert.equal(__registered[0].user,'B');assert.equal(__registered[0].platform,'android');assert.equal(__prefs.length,1);
 await m.nativePushOptOut();assert.equal(m.nativePushRegistered(),false);assert.equal(__removed.length,1);
 await m.nativePushLogout();assert.equal(__sdkUser,null);console.log('PASS interrupted account A login, logout, account B login, one native registration, explicit opt-in, opt-out and identity cleanup');
}finally{await rm(temp,{recursive:true,force:true});}
