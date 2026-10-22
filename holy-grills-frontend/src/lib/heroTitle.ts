/**
 * Hero headline split — white opening, gradient finish.
 * ============================================================================
 * The homepage hero used to paint the whole title with the brand gradient. The
 * reference design keeps the first phrase plain white and only then lets the
 * colour bloom, so the headline reads as white copy that warms up rather than
 * as a gradient that happens to start on a letter.
 *
 * The split is copy-driven, never hardcoded:
 *   1. an explicit line break in the CMS headline is the strongest signal;
 *   2. otherwise the first sentence — including its own closing punctuation,
 *      which is what makes "eat." still read as white;
 *   3. otherwise the first comma-separated clause;
 *   4. otherwise an even word split, so even a bare phrase still transitions.
 *
 * Pure and import-free, so `npm run test:hero-title` can exercise the real
 * module (esbuild transpiles it, exactly like the other lib tests).
 */

export interface HeroTitleParts {
  /** Rendered white. */
  lead: string;
  /** Rendered with the white → fire gradient. Empty when nothing is left. */
  tail: string;
}

const LINE_BREAK = /^([^\n]+)\n+([\s\S]+)$/;
const FIRST_SENTENCE = /^([\s\S]*?[.!?:;…])\s+([\s\S]+)$/;
const FIRST_CLAUSE = /^([\s\S]*?,)\s+([\s\S]+)$/;

export function heroTitleParts(title: unknown): HeroTitleParts {
  const text = typeof title === 'string' ? title.trim() : '';
  if (!text) return { lead: '', tail: '' };

  for (const pattern of [LINE_BREAK, FIRST_SENTENCE, FIRST_CLAUSE]) {
    const match = text.match(pattern);
    if (!match) continue;
    const lead = match[1].trim();
    const tail = match[2].trim();
    if (lead && tail) return { lead, tail };
  }

  const words = text.split(/\s+/);
  if (words.length < 2) return { lead: text, tail: '' };
  const split = Math.ceil(words.length / 2);
  return { lead: words.slice(0, split).join(' '), tail: words.slice(split).join(' ') };
}
