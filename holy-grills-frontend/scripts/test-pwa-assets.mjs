import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import sharp from 'sharp';
const manifest=JSON.parse(await readFile('public/manifest.json','utf8'));
assert.equal(manifest.display,'standalone');assert.equal(manifest.start_url,'/');
for(const icon of manifest.icons.filter(icon=>icon.type==='image/png')) {
 const image=sharp('public'+icon.src);const metadata=await image.metadata();
 assert.equal(`${metadata.width}x${metadata.height}`,icon.sizes);
 if(icon.purpose!=='maskable')continue;
 const {data,info}=await image.ensureAlpha().raw().toBuffer({resolveWithObject:true});
 let gold=0,maxRadius=0;
 for(let y=0;y<info.height;y++)for(let x=0;x<info.width;x++) {
  const index=(y*info.width+x)*4;assert.equal(data[index+3],255);
  if(data[index+1]>80){gold++;maxRadius=Math.max(maxRadius,Math.hypot((x+.5)/info.width-.5,(y+.5)/info.height-.5));}
 }
 assert.ok(gold>100,'gold S must be visible');assert.ok(maxRadius<=.4,`maskable artwork leaves safe circle: ${maxRadius}`);
}
console.log('PASS manifest PNG dimensions, visible full gold artwork, opaque maskable beds and 80%-diameter safe circle');
