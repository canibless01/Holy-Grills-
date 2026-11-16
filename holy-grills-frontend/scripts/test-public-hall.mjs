import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
const temp=await mkdtemp(join(tmpdir(),'hg-hall-'));
try {
 const file=join(temp,'hall.mjs');
 await build({entryPoints:['src/lib/publicHallEntries.ts'],bundle:true,format:'esm',outfile:file});
 const {publicHallEntries}=await import(pathToFileURL(file));
 const genuine={name:'Testimony F.'};
 const rows=[{name:'[TEST] userf'},{winner:{full_name:' [AUDIT PROVIDER] actor'}},genuine];
 assert.deepEqual(publicHallEntries(rows),[genuine]);assert.equal(rows.length,3);
 console.log('PASS public hall excludes labelled fixtures, retains genuine names and stored input');
}finally{await rm(temp,{recursive:true,force:true})}
