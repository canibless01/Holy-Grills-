/** Generate launcher assets from the supplied gold S; never crop its artwork.
 * Run from the frontend root: node scripts/generate-icons.mjs
 * Maskable artwork stays inside the central 80%-diameter safe circle.
 */
import sharp from 'sharp';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
const root=process.cwd();
const source=path.join(root,'public','brand','HG_Favicon.png');
const directory=path.join(root,'public','icons');
const red='#E70E0E';
await mkdir(directory,{recursive:true});
async function icon(size, fraction, file) {
  const box=Math.floor(size*fraction);
  const artwork=await sharp(source).resize(box,box,{fit:'inside'}).png().toBuffer();
  await sharp({create:{width:size,height:size,channels:4,background:red}})
    .composite([{input:artwork,gravity:'centre'}]).png().toFile(path.join(directory,file));
}
for(const size of [16,32,192,512]) await icon(size,size<=32?0.88:0.8,`icon-${size}.png`);
for(const size of [192,512]) await icon(size,0.55,`maskable-${size}.png`);
await icon(180,0.72,'apple-touch-icon.png');
const artwork=await sharp(source).resize(410,410,{fit:'inside'}).png().toBuffer();
await writeFile(path.join(directory,'icon.svg'),`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" rx="100" fill="${red}"/><image href="data:image/png;base64,${artwork.toString('base64')}" x="51" y="51" width="410" height="410" preserveAspectRatio="xMidYMid meet"/></svg>\n`);
console.log('Generated complete gold S on brand red; maskable artwork uses the safe circle.');
