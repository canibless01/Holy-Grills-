/**
 * bannerSpec tests — the one source of truth for banner frames.
 * ============================================================================
 * src/lib/bannerSpec.ts decides both what shape every card draws and what size
 * an administrator is told to design to. The admin note reads the same numbers,
 * so a mismatch here is a mismatch the CMS would publish to designers.
 *
 *   npm run test:banner-spec
 */
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const out = join(root, 'node_modules', '.cache-banner-spec.mjs');
execFileSync(join(root, 'node_modules', '.bin', 'esbuild'), [
  join(root, 'src', 'lib', 'bannerSpec.ts'),
  '--loader:.ts=ts',
  '--format=esm',
  `--outfile=${out}`,
]);
writeFileSync(out, readFileSync(out, 'utf8').replace(/from "[^"]*"/g, () => { throw new Error('unexpected import'); }));

const {
  BANNER_SPECS, BANNER_ICON_SIZE, bannerSpec, storefrontSpecId, bannerPlacementSpecId, promoSpecId,
} = await import(out);

let failures = 0;
const eq = (label, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures += 1;
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${ok ? '' : ` — got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`}`);
};

const gcd = (a, b) => (b === 0 ? a : gcd(b, a % b));
const ratioOf = (spec) => {
  const d = gcd(spec.width, spec.height);
  return `${spec.width / d}:${spec.height / d}`;
};

console.log('BANNER_SPECS');
for (const [id, spec] of Object.entries(BANNER_SPECS)) {
  eq(`${id}: id matches its key`, spec.id, id);
  eq(`${id}: layout is known`, ['row', 'stack'].includes(spec.layout), true);
  eq(`${id}: published ratio matches its size`, spec.ratio, ratioOf(spec));
  eq(`${id}: aspect-ratio mirrors the design size`, spec.aspect, `${spec.width / gcd(spec.width, spec.height)} / ${spec.height / gcd(spec.width, spec.height)}`);
  eq(`${id}: size is whole pixels`, [spec.width, spec.height].every((n) => Number.isInteger(n) && n > 0), true);
  eq(`${id}: longest edge is a 2x-friendly width`, spec.width >= 1200, true);
}
eq('icon frame stays square', [BANNER_ICON_SIZE, Number.isInteger(BANNER_ICON_SIZE), BANNER_ICON_SIZE >= 128], [256, true, true]);

console.log('\nbannerSpec fallback');
eq('known id resolves', bannerSpec('strip').id, 'strip');
eq('unknown id falls back instead of crashing', bannerSpec('nope').id, 'feature');
eq('undefined id falls back', bannerSpec(undefined).id, 'feature');

console.log('\nsurface mapping');
eq('What\'s Inside → compact row frame', storefrontSpecId('compact'), 'compact');
eq('Promos on menu → 4:1 strip', storefrontSpecId('banner'), 'strip');
eq('How It\'s Made → stacked 3:2', storefrontSpecId('landscape'), 'feature');
eq('Promos on home/checkout → stacked 3:2', storefrontSpecId('poster'), 'feature');
eq('unknown variant → stacked 3:2', storefrontSpecId('nope'), 'feature');
eq('home banners → 3:1', bannerPlacementSpecId('home'), 'wide');
eq('menu banners → 4:1', bannerPlacementSpecId('menu'), 'strip');
eq('checkout banners → 4:1', bannerPlacementSpecId('checkout'), 'strip');
eq('promo on menu → 4:1', promoSpecId('menu'), 'strip');
eq('promo on home → 3:2', promoSpecId('home'), 'feature');
eq('promo on checkout → 3:2', promoSpecId('checkout'), 'feature');

console.log('\npublished design sizes');
eq('What\'s Inside artwork', `${BANNER_SPECS.compact.width} × ${BANNER_SPECS.compact.height}`, '1200 × 400');
eq('How It\'s Made / Promos artwork', `${BANNER_SPECS.feature.width} × ${BANNER_SPECS.feature.height}`, '1200 × 800');
eq('Home banner artwork', `${BANNER_SPECS.wide.width} × ${BANNER_SPECS.wide.height}`, '1200 × 400');
eq('Menu / checkout banner artwork', `${BANNER_SPECS.strip.width} × ${BANNER_SPECS.strip.height}`, '1600 × 400');

rmSync(out, { force: true });
console.log(failures === 0 ? '\nHELPER: all assertions pass' : `\nHELPER: ${failures} FAILURES`);
process.exit(failures === 0 ? 0 : 1);
