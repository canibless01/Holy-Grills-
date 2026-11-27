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
