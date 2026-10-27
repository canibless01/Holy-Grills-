import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { rmSync } from 'node:fs';
import assert from 'node:assert/strict';
const root=join(dirname(fileURLToPath(import.meta.url)),'..');
const out=join(root,'node_modules','.cache-rider-navigation.mjs');
execFileSync(join(root,'node_modules','.bin','esbuild'),[join(root,'src/lib/riderNavigation.ts'),'--bundle','--format=esm',`--outfile=${out}`]);
try {
 const {riderNavigationUrl}=await import(out);
 const destination=order=>new URL(riderNavigationUrl(order)).searchParams.get('destination');
 assert.equal(destination({delivery_location_lat:6.51,delivery_location_lon:3.38,delivery_address:'Other address'}),'6.51,3.38');
 assert.equal(destination({delivery_location_lat:0,delivery_location_lon:0}),'0,0');
 assert.equal(destination({delivery_address_snapshot:{lat:'7.3',lng:'5.1'}}),'7.3,5.1');
 assert.equal(destination({delivery_location_lat:NaN,delivery_location_lon:500,delivery_address:'Ikeja, Lagos'}),'Ikeja, Lagos');
 assert.equal(destination({delivery_address_snapshot:{line1:'Street & junction',landmark:'Blue shop'}}),'Street & junction, Blue shop');
 assert.equal(riderNavigationUrl({delivery_location_lat:null,delivery_location_lon:''}),null);
 assert.equal(riderNavigationUrl({}),null);
 assert.equal(riderNavigationUrl({delivery_location_lat:true,delivery_location_lon:false}),null);
 console.log('8 rider destination checks passed');
} finally {rmSync(out,{force:true});}
