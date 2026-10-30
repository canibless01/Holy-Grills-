/** A WhatsApp tap opens its text composer; it must never open a Cloudinary image. */
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
const temp=await mkdtemp(join(tmpdir(),'hg-whatsapp-'));
try {
  const file=join(temp,'share.mjs');
  await build({entryPoints:['src/lib/whatsappShare.ts'],bundle:true,format:'esm',outfile:file});
  const opened=[];
  globalThis.window={open:(...args)=>opened.push(args)};
  const {openWhatsApp}=await import(pathToFileURL(file));
  const caption='Bring your people ❤️‍🔥 https://holygrills.online/?ref=MYCODE&source=promo';
  openWhatsApp(caption);
  assert.equal(opened.length,1);
  const url=new URL(opened[0][0]);
  assert.equal(url.hostname,'wa.me');
  assert.equal(url.searchParams.get('text'),caption);
  assert.equal(url.searchParams.has('image'),false);
  assert.equal(opened[0][2],'noopener,noreferrer');
  const source=await readFile('src/components/admin/AdminAmbassadorPromo.tsx','utf8');
  assert.ok(source.includes('openWhatsApp(caption)'));
  assert.ok(source.includes('/?ref='));
  assert.ok(['pending','seen','shared'].every(status=>source.includes(`'${status}'`)));
  assert.ok(!/read[_-]?receipt|delivery[_-]?receipt/i.test(source));
  console.log('PASS WhatsApp composer preserves personalized text/link; graphic saving stays separate; no fake receipts');
} finally {await rm(temp,{recursive:true,force:true});}
