/**
 * heroTitle tests — the white → gradient headline split.
 * ============================================================================
 * src/lib/heroTitle.ts decides where the hero headline stops being white and
 * starts flowing into the brand gradient. The boundary must be punctuation (or
 * an explicit line break) so the two colours meet at a hard edge and never
 * blend; these cases pin the copy shapes the CMS actually produces, including
 * the punctuation that has to stay in the white run.
 *
 * Exercised against the real module the same way test-value-text does it:
 * esbuild transpiles it, no test framework is added for one file.
 *
 *   npm run test:hero-title
 */
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const out = join(root, 'node_modules', '.cache-hero-title.mjs');
execFileSync(join(root, 'node_modules', '.bin', 'esbuild'), [
  join(root, 'src', 'lib', 'heroTitle.ts'),
  '--loader:.ts=ts',
  '--format=esm',
  `--outfile=${out}`,
]);
// The module must stay import-free: that is what keeps it testable here.
writeFileSync(out, readFileSync(out, 'utf8').replace(/from "[^"]*"/g, () => { throw new Error('unexpected import'); }));

const { heroTitleParts } = await import(out);

let failures = 0;
const eq = (label, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures += 1;
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${label}${ok ? '' : ` — got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`}`);
};

console.log('heroTitleParts — punctuation boundary');
eq('full stop stays white, gradient starts on the next word', heroTitleParts('Eat fresh. Feel the fire.'),
  { lead: 'Eat fresh.', tail: 'Feel the fire.' });
eq('comma is the boundary too', heroTitleParts('Good food, good mood'),
  { lead: 'Good food,', tail: 'good mood' });
eq('earliest punctuation wins over a later one', heroTitleParts('Eat, drink, repeat.'),
  { lead: 'Eat,', tail: 'drink, repeat.' });
eq('question mark stays white', heroTitleParts('Hungry? We deliver.'),
  { lead: 'Hungry?', tail: 'We deliver.' });
eq('exclamation mark stays white', heroTitleParts('Fire! Fresh plates daily.'),
  { lead: 'Fire!', tail: 'Fresh plates daily.' });
eq('ellipsis stays white', heroTitleParts('Still hungry… Then order.'),
  { lead: 'Still hungry…', tail: 'Then order.' });
eq('colon stays white', heroTitleParts('Two rules: eat well, eat often.'),
  { lead: 'Two rules:', tail: 'eat well, eat often.' });
eq('multi-punctuation cluster stays together', heroTitleParts('Really?! Yes, really.'),
  { lead: 'Really?!', tail: 'Yes, really.' });

console.log('\nheroTitleParts — line break and no-boundary fallbacks');
eq('a line break is a clean boundary', heroTitleParts("Fresh off the grill\nToday's specials."),
  { lead: 'Fresh off the grill', tail: "Today's specials." });
eq('multi-line copy joins into one gradient run', heroTitleParts('Line one\nLine two\nLine three'),
  { lead: 'Line one', tail: 'Line two\nLine three' });
eq('punctuation beats a line break', heroTitleParts('Eat well.\nThen rest'),
  { lead: 'Eat well.', tail: 'Then rest' });
eq('no punctuation at all keeps the whole title white', heroTitleParts('Fire grilled flavour'),
  { lead: 'Fire grilled flavour', tail: '' });
eq('trailing full stop means everything is white', heroTitleParts('Holy Grills.'),
  { lead: 'Holy Grills.', tail: '' });
eq('single word is all white', heroTitleParts('Fire'), { lead: 'Fire', tail: '' });
eq('surrounding whitespace is trimmed', heroTitleParts('  Big flavours.  Bigger portions.  '),
  { lead: 'Big flavours.', tail: 'Bigger portions.' });
eq('punctuation without following copy stays white', heroTitleParts('Served hot, '),
  { lead: 'Served hot,', tail: '' });

console.log('\nheroTitleParts — input handling');
eq('empty copy is empty', heroTitleParts(''), { lead: '', tail: '' });
eq('whitespace-only copy is empty', heroTitleParts('   \n  '), { lead: '', tail: '' });
eq('null is empty', heroTitleParts(null), { lead: '', tail: '' });
eq('undefined is empty', heroTitleParts(undefined), { lead: '', tail: '' });
eq('non-string is empty', heroTitleParts({ title: 'Fire' }), { lead: '', tail: '' });
eq('no copy is lost across the split', (() => {
  const { lead, tail } = heroTitleParts('Eat. Earn. Come back.');
  return `${lead} ${tail}`;
})(), 'Eat. Earn. Come back.');

rmSync(out, { force: true });
console.log(failures === 0 ? '\nHELPER: all assertions pass' : `\nHELPER: ${failures} FAILURES`);
process.exit(failures === 0 ? 0 : 1);
