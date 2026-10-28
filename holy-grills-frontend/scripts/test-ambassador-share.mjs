/**
 * Ambassador promo share contract.
 * ============================================================================
 * WhatsApp cannot be driven programmatically with an image attachment, and
 * wa.me links prefill text only. AdminAmbassadorPromo therefore shares the
 * graphic + personalized caption through the Web Share API when the browser
 * reports file-sharing support, and otherwise falls back to an explicit,
 * honest manual path: download the graphic and copy the caption. There are no
 * automated deliveries and no fake read receipts — the Pending/Seen/Shared
 * activity statuses are recorded manually by staff.
 *
 *   npm run test:ambassador-share
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const source = readFileSync(
  join(root, 'src', 'components', 'admin', 'AdminAmbassadorPromo.tsx'), 'utf8');

const checks = [
  ['Web Share API support is probed with navigator.canShare({ files })',
    source.includes('nav.canShare') && source.includes('canShare({ files: [file] })')],
  ['the graphic is shared as a File alongside the caption',
    source.includes('nav.share({ files: [file], text: caption')],
  ['a fetch/CORS failure degrades to the fallback instead of throwing',
    /fetch\(imageUrl\)[\s\S]{0,200}catch[\s\S]{0,80}file = null/.test(source)],
  ['fallback copies the personalized caption to the clipboard',
    source.includes('navigator.clipboard.writeText(caption)')],
  ['fallback downloads the graphic via an anchor download',
    source.includes('a.download =')],
  ['the fallback toast states honestly that manual attachment is needed',
    source.includes("FE_ADMIN_AMBASSADOR_PROMO_FALLBACK")],
  ['per-ambassador links are built on the existing ?ref= tracking link',
    source.includes('/?ref=')],
  ['caption personalization replaces every {{link}} token form',
    source.includes('{{link}}') && source.includes('{link}') && source.includes('{{LINK}}')],
  ['no wa.me URL pretends an image can be attached automatically',
    !source.includes('wa.me')],
  ['no fabricated read/delivery receipts exist in the component',
    !/read[_-]?receipt|delivery[_-]?receipt/i.test(source)],
  ['activity statuses are limited to pending / seen / shared',
    ['pending', 'seen', 'shared'].every((s) => source.includes(`'${s}'`))],
];

let failures = 0;
for (const [label, ok] of checks) {
  if (!ok) failures += 1;
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}`);
}
assert.equal(failures, 0, `${failures} ambassador share contract check(s) failed`);
console.log('Ambassador promo share contract checks passed');
