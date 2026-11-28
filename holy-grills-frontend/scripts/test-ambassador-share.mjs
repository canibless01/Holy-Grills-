/** WhatsApp links target the recipient without changing the caption or opening an image. */
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
const temp=await mkdtemp(join(tmpdir(),'hg-whatsapp-'));
try {
  const file=join(temp,'share.mjs');
  await build({entryPoints:['src/lib/whatsappShare.ts'],bundle:true,format:'esm',outfile:file});
  const {buildWhatsAppShareUrl}=await import(pathToFileURL(file));
  const caption='Bring your people ❤️‍🔥 https://holygrills.online/?ref=MYCODE&source=promo';
  for(const [phone,path] of [['08012345678','/2348012345678'],['+234 801 234 5678','/2348012345678'],['+44 7700 900123','/447700900123'],[null,'/'],['invalid','/'],['123','/']]) {
    const url=new URL(buildWhatsAppShareUrl(caption,phone));
    assert.equal(url.origin,'https://wa.me');
    assert.equal(url.pathname,path);
    assert.equal(url.searchParams.get('text'),caption);
    assert.equal(url.searchParams.has('image'),false);
  }
  console.log('PASS direct recipient links, local/international normalization, missing-phone chooser and exact caption preservation');
} finally {await rm(temp,{recursive:true,force:true});}
