import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
const temp=await mkdtemp(join(tmpdir(),'hg-catalog-'));
const realNow=Date.now;
try {
 const file=join(temp,'client.mjs');
 await build({entryPoints:['src/lib/apiClient.ts'],bundle:true,format:'esm',platform:'node',outfile:file,define:{'import.meta.env.VITE_API_BASE_URL':'"https://test.invalid/api"'}});
 const store=()=>{const m=new Map();return{getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)}};
 globalThis.window={localStorage:store(),sessionStorage:store()};
 let calls=0,now=1000,fail=false,defer=false,release;
 Date.now=()=>now;
 globalThis.fetch=async()=>{
  calls++; const value={sequence:calls,items:[{name:'Original'}]};
  if(defer){defer=false;await new Promise(resolve=>release=resolve);}
  if(fail){fail=false;return new Response('{"error":"Unavailable"}',{status:503});}
  return new Response(JSON.stringify(value),{status:200,headers:{'content-type':'application/json'}});
 };
 const {apiClient,setTokens,clearTokens}=await import(pathToFileURL(file));
 const catalog=()=>apiClient.get('/menu/items',undefined,undefined,{cacheMs:15000});
 const a=await catalog();a.items[0].name='Edited';
 assert.equal((await catalog()).items[0].name,'Original');assert.equal(calls,1);
 now+=15001;await catalog();assert.equal(calls,2);
 window.localStorage.setItem('hg_campus_id','other');await catalog();assert.equal(calls,3);
 setTokens('account-a','refresh');await catalog();assert.equal(calls,4);
 setTokens('account-b','refresh');await catalog();assert.equal(calls,5);
 clearTokens();await catalog();assert.equal(calls,6);
 await apiClient.post('/cart',{quantity:1});await catalog();assert.equal(calls,8);
 await apiClient.get('/wallet');await apiClient.get('/wallet');assert.equal(calls,10);
 defer=true;const old=apiClient.get('/menu/items',{q:'race'},undefined,{cacheMs:15000});
 await apiClient.patch('/menu/items/1',{is_available:false});release();await old;
 const before=calls;await apiClient.get('/menu/items',{q:'race'},undefined,{cacheMs:15000});assert.equal(calls,before+1);
 fail=true;await assert.rejects(apiClient.get('/menu/items',{q:'error'},undefined,{cacheMs:15000}));
 const after=calls;await apiClient.get('/menu/items',{q:'error'},undefined,{cacheMs:15000});assert.equal(calls,after+1);
 console.log('PASS catalogue TTL and copy isolation; campus/account isolation; mutation and late-read invalidation; errors and financial reads stay fresh');
} finally {Date.now=realNow;await rm(temp,{recursive:true,force:true});}
