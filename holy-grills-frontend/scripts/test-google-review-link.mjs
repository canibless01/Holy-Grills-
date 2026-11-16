import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
const temp=await mkdtemp(join(tmpdir(),'hg-review-'));
try {
 const file=join(temp,'review.mjs');await build({entryPoints:['src/lib/googleReviews.ts'],bundle:true,format:'esm',platform:'node',outfile:file});
 const {googleReviewUrl}=await import(pathToFileURL(file));
 const direct='https://g.page/r/CT3sD6yYtneQECA/review';
 assert.equal(googleReviewUrl({reviewUrl:direct}),direct);
 assert.equal(googleReviewUrl({reviewUrl:direct,placeId:'legacy-id'}),direct);
 assert.equal(googleReviewUrl({placeId:'ChIJ example'}),'https://search.google.com/local/writereview?placeid=ChIJ%20example');
 assert.equal(googleReviewUrl(),null);
 for(const reviewUrl of ['javascript:alert(1)','http://g.page/r/test/review','https://g.page.attacker.invalid/r/review','https://attacker.invalid/review','https://user:password@g.page/review','https://google.com/url?q=https://attacker.invalid'])assert.equal(googleReviewUrl({reviewUrl}),null);
 assert.equal(googleReviewUrl({reviewUrl:'bad',placeId:'existing'}),'https://search.google.com/local/writereview?placeid=existing');
 console.log('PASS direct review link without API/Place ID; legacy fallback; invalid destinations excluded');
}finally{await rm(temp,{recursive:true,force:true})}
