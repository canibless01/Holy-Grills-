import { execFileSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { rmSync } from 'node:fs';
import assert from 'node:assert/strict';
const root=join(dirname(fileURLToPath(import.meta.url)),'..');const out=join(root,'node_modules','.cache-challenge-steps.mjs');
execFileSync(join(root,'node_modules','.bin','esbuild'),[join(root,'src/lib/challengeProgression.ts'),'--format=esm',`--outfile=${out}`]);
try {
 const {nextChallengeSteps:next}=await import(out);
 const row=(id,target,trigger='referral_count',period=null)=>({id,trigger_value:target,trigger_type:trigger,time_window:period});
 const one=row('r1',1,'first_referral'),five=row('r5',5),ten=row('r10',10),order=row('o3',3,'order_count');
 assert.deepEqual(next([ten,five,order,one],[]).map(x=>x.id),['r1','o3']);
 assert.deepEqual(next([five,ten,order],[one]).map(x=>x.id),['r5','o3']);
 assert.deepEqual(next([one,five,ten],[one,five]).map(x=>x.id),['r10']);
 assert.equal(next([five,row('weekly',2,'referral_count','weekly'),row('monthly',2,'referral_count','monthly')],[]).length,3);
 assert.equal(next([{...five,campus_id:'a'},{...five,id:'b',campus_id:'b'}],[]).length,2);
 assert.equal(next([row('ig',1,'social_follow'),row('wa',1,'social_follow')],[]).length,2);
 assert.equal(next([row('unknown1',1,''),row('unknown2',1,'')],[]).length,2);
 console.log('PASS progressive referral targets, claim advancement, independent activities/periods/campuses/social actions and unknown definitions');
} finally {rmSync(out,{force:true});}
