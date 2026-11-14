import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
const temp=await mkdtemp(join(tmpdir(),'hg-registration-'));
const realNow=Date.now;
try {
 const file=join(temp,'options.mjs');
 await build({entryPoints:['src/lib/registrationOptions.ts'],bundle:true,format:'esm',platform:'node',outfile:file,define:{'import.meta.env.VITE_API_BASE_URL':'"https://test.invalid/api"'}});
 const store=()=>{const m=new Map();return{getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)}};
 globalThis.window={localStorage:store(),sessionStorage:store()};
 let calls=0,now=1000,statuses=[503,200];Date.now=()=>now;
 globalThis.fetch=async url=>{
  calls++;const status=statuses.shift()||200;
  const campus=new URL(url).searchParams.get('campus_id')||'campus-a';
  return new Response(JSON.stringify(status===200?{campus_id:campus,campuses:[],departments:[{name:'Original'}],levels:[]}:{error:'Unavailable'}),{status,headers:{'content-type':'application/json'}});
 };
 const {registrationOptions}=await import(pathToFileURL(file));
 const [a,b]=await Promise.all([registrationOptions(),registrationOptions()]);
 assert.equal(calls,2,'one shared request plus one retry');a.departments[0].name='Changed';assert.equal(b.departments[0].name,'Original');
 assert.equal((await registrationOptions({campus_id:'campus-a'})).departments[0].name,'Original');assert.equal(calls,2);
 await registrationOptions({campus_id:'campus-b'});assert.equal(calls,3);
 window.localStorage.setItem('hg_campus_id','campus-b');await registrationOptions();assert.equal(calls,3,'implicit campus uses matching snapshot');
 await registrationOptions({campus_id:'campus-b'},true);assert.equal(calls,4,'Retry bypasses saved data');
 now+=60001;statuses=[400];await assert.rejects(registrationOptions({campus_id:'campus-b'}));assert.equal(calls,5,'400 never retried or hidden by expired cache');
 statuses=[503,503];await assert.rejects(registrationOptions({campus_id:'campus-c'}));assert.equal(calls,7,'bounded retry');
 await registrationOptions({campus_id:'campus-c'});assert.equal(calls,8,'failed read not cached');
 console.log('PASS signup snapshot coalescing, transient recovery, campus scope, storage reload, TTL, force and bounded errors');
} finally {Date.now=realNow;await rm(temp,{recursive:true,force:true});}
