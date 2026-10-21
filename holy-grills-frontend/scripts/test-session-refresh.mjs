import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
const stores = { localStore: new Map(), sessionStore: new Map() };
for (const store of Object.values(stores)) { store.getItem = key => store.get(key) ?? null; store.setItem = (key,value) => store.set(key,value); store.removeItem = key => store.delete(key); }
globalThis.__sessionStores = stores;
let source = readFileSync(new URL('../src/lib/apiClient.ts',import.meta.url),'utf8')
  .replace("import { localStore, sessionStore } from '@/lib/storage';", 'const {localStore,sessionStore}=globalThis.__sessionStores;')
  .replace('import.meta.env.VITE_API_BASE_URL', "'http://session.test/api'");
const output = ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText;
const api = await import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);
const json = (status,body) => new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}});
api.setTokens('expired','refresh-one');let rotations=0;
globalThis.fetch = async (url,opts) => {
 if(url.endsWith('/auth/refresh')) { rotations++; await new Promise(r=>setTimeout(r,20)); return json(200,{access_token:'fresh',refresh_token:'refresh-two'}); }
 if(opts.headers.Authorization==='Bearer expired') { if(url.endsWith('/late')) await new Promise(r=>setTimeout(r,60)); return json(401,{error:'expired'}); }
 assert.equal(opts.headers.Authorization,'Bearer fresh');return json(200,{ok:true});
};
assert.deepEqual(await Promise.all(['/one','/two','/late'].map(p=>api.apiClient.get(p))),[{ok:true},{ok:true},{ok:true}]);assert.equal(rotations,1);
api.setTokens('expired','refresh-outage');
globalThis.fetch=async url=>url.endsWith('/auth/refresh')?json(503,{error:'cold'}):json(401,{error:'expired'});
await assert.rejects(api.apiClient.get('/me'),e=>e.status===503);assert.equal(api.getRefreshToken(),'refresh-outage');
globalThis.fetch=async url=>url.endsWith('/auth/refresh')?json(200,{unexpected:true}):json(401,{error:'expired'});
await assert.rejects(api.apiClient.get('/me'),e=>e.status===0);assert.equal(api.getRefreshToken(),'refresh-outage');
let release;globalThis.fetch=async url=>url.endsWith('/auth/refresh')?new Promise(resolve=>{release=()=>resolve(json(200,{access_token:'stale',refresh_token:'stale-refresh'}));}):json(401,{error:'expired'});
const pending=api.apiClient.get('/me');while(!release) await new Promise(r=>setTimeout(r,1));api.clearTokens();release();
await assert.rejects(pending,e=>e.status===0);assert.equal(api.getToken(),null);
api.setTokens('old-account','old-refresh');
let rejectOld, calls=0;
globalThis.fetch=async()=>{calls++;return new Promise(resolve=>{rejectOld=()=>resolve(json(401,{error:'expired'}));});};
const oldAction=api.apiClient.post('/order',{item:'old-account'});while(!rejectOld) await new Promise(r=>setTimeout(r,1));
api.setTokens('new-account','new-refresh');rejectOld();
await assert.rejects(oldAction,e=>e.status===0);assert.equal(calls,1,'old action must never retry under a newly signed-in identity');
console.log('PASS session refresh concurrency, late 401 reuse, outages, malformed replies and logout race');
