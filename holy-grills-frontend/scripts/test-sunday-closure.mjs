import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
const temp=await mkdtemp(join(tmpdir(),'hg-sunday-'));
try {
 const file=join(temp,'sunday.mjs');
 await build({entryPoints:['src/lib/sundayClosure.ts'],bundle:true,format:'esm',platform:'node',outfile:file});
 const {closureDay,sundayOffer,sundayDismissKey}=await import(pathToFileURL(file));
 const stamp=value=>Date.parse(value);
 assert.equal(closureDay(stamp('2026-11-07T22:59:59Z')).sunday,false);
 assert.equal(closureDay(stamp('2026-11-07T23:00:00Z')).sunday,true);
 assert.equal(closureDay(stamp('2026-11-08T22:59:59Z')).sunday,true);
 assert.equal(closureDay(stamp('2026-11-08T23:00:00Z')).sunday,false);
 assert.equal(sundayOffer('2026-11-09',stamp('2026-11-08T12:00:00Z')).mondayNext,true);
 assert.equal(sundayOffer('2026-11-10',stamp('2026-11-08T12:00:00Z')).mondayNext,false);
 assert.equal(sundayOffer(undefined,stamp('2026-11-08T12:00:00Z')).mondayNext,false);
 assert.notEqual(sundayDismissKey('campus-a','2026-11-08'),sundayDismissKey('campus-b','2026-11-08'));
 assert.notEqual(sundayDismissKey('campus-a','2026-11-08'),sundayDismissKey('campus-a','2026-11-15'));
 assert.notEqual(sundayDismissKey('campus-a','2026-11-08'),'hg_kc_dismissed');
 console.log('PASS WAT Sunday boundaries; Monday availability; unknown/full-day fallback; dismissal isolated by day/campus');
} finally {await rm(temp,{recursive:true,force:true});}
