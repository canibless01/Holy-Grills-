import { build } from 'esbuild';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL,fileURLToPath } from 'node:url';
const temp=await mkdtemp(join(tmpdir(),'hg-guest-consent-'));
try {
 const file=join(temp,'consent.mjs');
 await build({entryPoints:[fileURLToPath(new URL('../src/lib/pushGuestConsent.ts',import.meta.url))],outfile:file,bundle:true,format:'esm',platform:'node'});
 const {canAdoptGuestPushConsent:can}=await import(pathToFileURL(file));
 const now=Date.parse('2026-11-25T12:00:00Z');const optIn=now-10*86400000;
 assert.equal(can(new Date(now-10000).toISOString(),optIn,now),true,'new account can adopt an older valid device opt-in');
 assert.equal(can(new Date(optIn-10000).toISOString(),optIn,now),false,'older account opt-out is untouched');
 assert.equal(can(undefined,optIn,now),false);assert.equal(can('invalid',optIn,now),false);assert.equal(can(new Date(now).toISOString(),0,now),false);
 assert.equal(can(new Date(now).toISOString(),now+1,now),false);
 console.log('PASS: new-account guest-consent adoption, existing-account opt-outs and invalid timestamps');
} finally {await rm(temp,{recursive:true,force:true});}
