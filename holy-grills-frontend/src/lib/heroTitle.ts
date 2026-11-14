/**
 * Hero headline split — white up to the punctuation, gradient after it.
 * ============================================================================
 * The homepage hero keeps its opening phrase plain white and only then starts
 * the brand gradient. The boundary is a **punctuation mark**, never a colour
 * fade: the white run ends (and the punctuation itself belongs to the white
 * run), then the gradient begins on the next word. Nothing is blended — there
 * is no cream stop or white-to-red ramp between the two halves.
 *
 * Resolution order, all copy-driven:
 *   1. the earliest punctuation cluster (, . ; : ! ? …) followed by a space;
 *   2. an explicit line break in the CMS headline;
 *   3. no boundary at all — the whole title stays white (no gradient is forced
 *      onto a phrase that has nowhere clean to break).
 *
 * Pure and import-free, so `npm run test:hero-title` can exercise the real
 * module (esbuild transpiles it, exactly like the other lib tests).
 */

export interface HeroTitleParts {
  /** Rendered white, punctuation included. */
  lead: string;
  /** Rendered with the brand gradient. Empty when there is no boundary. */
  tail: string;
}

/** Earliest punctuation cluster that is followed by whitespace and more copy. */
const PUNCTUATION_BOUNDARY = /^([\s\S]*?[,.;:!?…]+)\s+([\s\S]+)$/;
const LINE_BREAK = /^([^\n]+)\n+([\s\S]+)$/;

export function heroTitleParts(title: unknown): HeroTitleParts {
  const text = typeof title === 'string' ? title.trim() : '';
  if (!text) return { lead: '', tail: '' };

  for (const pattern of [PUNCTUATION_BOUNDARY, LINE_BREAK]) {
    const match = text.match(pattern);
    if (!match) continue;
    const lead = match[1].trim();
    const tail = match[2].trim();
    if (lead && tail) return { lead, tail };
  }

  // No punctuation and no line break: keep the headline white rather than
  // inventing a boundary somewhere inside a word run.
  return { lead: text, tail: '' };
}
