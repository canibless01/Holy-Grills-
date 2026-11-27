import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
const dir=await mkdtemp(join(tmpdir(),'hg-recovery-'));
try {
 const compile=async(name,key='test-browser-key')=>{
  const output=join(dir,name.replaceAll('/','-')+key+'.mjs');
  await build({entryPoints:['src/'+name+'.ts'],outfile:output,bundle:true,platform:'node',format:'esm',define:{'import.meta.env.VITE_GOOGLE_MAPS_API_KEY':JSON.stringify(key)}});
  return import(pathToFileURL(output));
 };
 globalThis.window=Object.assign(new EventTarget(),{scrollY:0});
 let modal=false;globalThis.document={querySelector:()=>modal?{}:null};
 globalThis.Element=class { constructor(blocked=false,parent=null){this.blocked=blocked;this.parentElement=parent;this.scrollTop=0;} closest(){return this.blocked?this:null;} };
 const {installPullRefresh}=await compile('native/pullRefresh');
 let refreshes=0,progress=0,release;const stop=installPullRefresh(n=>progress=n,async()=>{refreshes++;await new Promise(r=>release=r)});
 const touch=(type,x,y,target=new Element(),count=1)=>{
  const e=new Event(type,{cancelable:true});Object.defineProperties(e,{touches:{value:Array.from({length:count},()=>({clientX:x,clientY:y}))},target:{value:target}});window.dispatchEvent(e);return e;
 };
 touch('touchstart',0,0);touch('touchmove',0,50);assert.equal(progress,50);touch('touchend',0,50);assert.equal(refreshes,0);
 touch('touchstart',0,0);assert.equal(touch('touchmove',0,100).defaultPrevented,true);touch('touchend',0,100);assert.equal(refreshes,1);
 touch('touchstart',0,0);touch('touchmove',0,100);touch('touchend',0,100);assert.equal(refreshes,1);release();await new Promise(r=>setImmediate(r));
 for(const blocked of [new Element(true),Object.assign(new Element(),{scrollTop:10})]){touch('touchstart',0,0,blocked);touch('touchmove',0,100);touch('touchend',0,100);}
 modal=true;touch('touchstart',0,0);modal=false;touch('touchmove',0,100);touch('touchend',0,100);
 window.scrollY=30;touch('touchstart',0,0);window.scrollY=0;touch('touchmove',0,100);touch('touchend',0,100);
 touch('touchstart',0,0);touch('touchmove',60,100);touch('touchend',60,100);
 touch('touchstart',0,0);touch('touchmove',0,100,new Element(),2);touch('touchend',0,100);
 touch('touchstart',0,0);touch('touchmove',0,100);touch('touchcancel',0,100);touch('touchend',0,100);
 assert.equal(refreshes,1);stop();assert.equal(progress,0);
 console.log('PASS pull-to-refresh threshold, busy coalescing and map/form/modal/scroll/pinch/cancellation guards');
 const {releasePlan}=await import('./android-release-plan.mjs');
 const plan=releasePlan({packageName:'com.holygrills.app',version:'1.0.2+30.1',versionCode:13001,sha256:'a'.repeat(64)},'canibless01/Holy-Grills-');
 assert.equal(plan.manifest.versionCode,13001);assert.equal(plan.tag,'android-v1.0.2-build-30.1');
 assert.throws(()=>releasePlan({packageName:'com.holygrills.app.debug'},'canibless01/Holy-Grills-'));
 console.log('PASS public release metadata, monotonic build labels and debug-publication rejection');
 const {createUpdateCheck}=await compile('native/updateChecks');
 let time=1000,saved=0,prompted=0,checks=0,updates=0,finish;
 const checker=createUpdateCheck({now:()=>time,lastSuccess:()=>saved,markSuccess:t=>saved=t,lastPrompt:()=>prompted,markPrompt:t=>prompted=t,getInfo:async()=>({id:'com.holygrills.app',build:'2'}),load:async()=>{checks++;return new Promise(r=>finish=r)},onUpdate:()=>updates++});
 const firstCheck=checker.check();await Promise.resolve();await checker.check();assert.equal(checks,1);finish(null);await firstCheck;
 time+=300001;const recovered=checker.check();await Promise.resolve();assert.equal(checks,2);finish({versionCode:3});await recovered;assert.equal(updates,1);
 time+=600000;await checker.check();assert.equal(checks,2);
 time+=86400001;const nextDay=checker.check();await Promise.resolve();assert.equal(checks,3);finish({versionCode:4});await nextDay;assert.equal(updates,1);
 const restored=createUpdateCheck({now:()=>time,lastSuccess:()=>0,markSuccess:()=>{},lastPrompt:()=>prompted,markPrompt:t=>prompted=t,getInfo:async()=>({id:'com.holygrills.app',build:'2'}),load:async()=>({versionCode:99}),onUpdate:()=>updates++});
 await restored.check();assert.equal(updates,1); // Persisted across remounts and upgrades.
 time=prompted+30*86400000;await restored.check();assert.equal(updates,2);
 time+=86400001;const interrupted=checker.check();await Promise.resolve();checker.stop();finish({versionCode:100});await interrupted;assert.equal(updates,2);
 console.log('PASS update resume coalescing, failed-network recovery, daily checks, persistent 30-day prompt limits and unmount safety');
 let scripts=[];document.createElement=()=>({dataset:{},remove(){this.removed=true;}});document.head={appendChild:script=>scripts.push(script)};
 const maps=await compile('lib/googleMaps');
 const first=maps.loadGoogleMaps();const joined=maps.loadGoogleMaps();assert.equal(first,joined);assert.equal(scripts.length,1);
 scripts[0].onerror();await assert.rejects(first,/maps_unavailable/);assert.equal(scripts[0].removed,true);
 const retry=maps.loadGoogleMaps();assert.equal(scripts.length,2);
 window.google={maps:{version:'test',importLibrary:async()=>({})}};window.__hgGoogleMapsReady();assert.equal(await retry,window.google.maps);
 await assert.rejects(maps.mapsDeadline(new Promise(()=>{}),5),/maps_timeout/);
 window.gm_authFailure();await assert.rejects(maps.loadGoogleMaps(),/maps_authentication/);assert.equal(scripts.length,2);
 delete window.google;const missing=await compile('lib/googleMaps','');await assert.rejects(missing.loadGoogleMaps(),/maps_not_configured/);
 console.log('PASS shared Google SDK load, real network retry, bounded library timeout and explicit missing/rejected key handling');
} finally {await rm(dir,{recursive:true,force:true});}
