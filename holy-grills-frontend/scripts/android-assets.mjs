// Reproducible Android resource sizes derived from the existing Holy Grills icon.
import sharp from 'sharp';
import { mkdir, writeFile } from 'node:fs/promises';
const root = 'android/app/src/main/res';
for (const [density, scale] of Object.entries({ mdpi:1, hdpi:1.5, xhdpi:2, xxhdpi:3, xxxhdpi:4 })) {
  const dir = `${root}/mipmap-${density}`; await mkdir(dir,{recursive:true});
  for (const name of ['ic_launcher','ic_launcher_round']) await sharp('public/icons/icon-512.png').resize(Math.round(48*scale)).png().toFile(`${dir}/${name}.png`);
  const side=Math.round(108*scale), inner=Math.round(64*scale);
  await sharp({create:{width:side,height:side,channels:4,background:'#E70E0E'}})
    .composite([{input:await sharp('public/icons/icon-512.png').resize(inner).toBuffer(),gravity:'center'}])
    .png().toFile(`${dir}/ic_launcher_foreground.png`);
}
await writeFile(`${root}/values/ic_launcher_background.xml`,'<resources><color name="ic_launcher_background">#E70E0E</color></resources>\n');
// Android notification small icons must be white alpha masks. Derive the mask
// from the existing gold mark, with the flat red background made transparent.
const size=72;
const {data,info}=await sharp('public/icons/icon-512.png').resize(size).ensureAlpha().raw().toBuffer({resolveWithObject:true});
for(let i=0;i<data.length;i+=info.channels){const alpha=Math.max(0,Math.min(255,(data[i+1]-35)*2));data[i]=255;data[i+1]=255;data[i+2]=255;data[i+3]=alpha;}
await sharp(data,{raw:{width:size,height:size,channels:4}}).png().toFile(`${root}/drawable/ic_stat_onesignal_default.png`);
await sharp('public/icons/icon-512.png').resize(256).png().toFile(`${root}/drawable/ic_onesignal_large_icon_default.png`);
console.log('Android launcher and monochrome notification assets generated from the existing brand mark');
