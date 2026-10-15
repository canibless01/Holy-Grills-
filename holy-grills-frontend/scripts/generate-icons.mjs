/**
 * generate-icons.mjs — builds the real PNG icon set from the brand flame SVG.
 *
 * Why: manifest.json and index.html used to ship SVG-only icons. A large share
 * of Android launchers and Chrome builds require real PNG sizes (192/512,
 * plus a maskable variant), and iOS requires PNG for apple-touch-icon — with
 * SVG-only icons those surfaces fall back to a generic tile, so the installed
 * app did not carry the brand mark.
 *
 * Outputs (public/icons/):
 *   icon-16.png / icon-32.png   favicon PNGs
 *   icon-192.png / icon-512.png manifest "any" icons
 *   apple-touch-icon.png        180×180 full-bleed (iOS rounds it itself)
 *   maskable-192.png / maskable-512.png  full-bleed with the flame inside the
 *                               80% safe zone (launcher masks can crop 20%)
 *
 * Run: node scripts/generate-icons.mjs   (idempotent, committed output)
 */
import sharp from 'sharp';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const outDir = path.join(root, 'public', 'icons');
const BRAND_BG = '#FF4E2D';

// The brand flame path lifted from public/icons/icon.svg (single source).
const { flameDefs, flamePath, corePath } = JSON.parse(
  await readFile(path.join(root, 'scripts', 'icon-flame.json'), 'utf8')
);

/** Rounded-square icon (favicon / any-purpose, mirrors icon.svg). */
const roundedSvg = (size) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="${size}" height="${size}">
  ${flameDefs}
  <rect width="512" height="512" rx="112" fill="${BRAND_BG}"/>
  ${flamePath}
  ${corePath}
</svg>`;

/** Full-bleed square (apple-touch / maskable base) with a scale factor for the art. */
const bleedSvg = (size, artScale) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="${size}" height="${size}">
  ${flameDefs}
  <rect width="512" height="512" fill="${BRAND_BG}"/>
  <g transform="translate(256 256) scale(${artScale}) translate(-256 -256)">
    ${flamePath}
    ${corePath}
  </g>
</svg>`;

const writePng = async (svg, file, size) => {
  await sharp(Buffer.from(svg)).resize(size, size).png().toFile(path.join(outDir, file));
  console.log('✓', file);
};

// Any-purpose (rounded, as-designed)
await writePng(roundedSvg(512), 'icon-192.png', 192);
await writePng(roundedSvg(512), 'icon-512.png', 512);
await writePng(roundedSvg(512), 'icon-32.png', 32);
await writePng(roundedSvg(512), 'icon-16.png', 16);
// Apple touch — full-bleed, art at 100%
await writePng(bleedSvg(180, 1), 'apple-touch-icon.png', 180);
// Maskable — art inside the 80% safe zone
await writePng(bleedSvg(512, 0.62), 'maskable-192.png', 192);
await writePng(bleedSvg(512, 0.62), 'maskable-512.png', 512);

console.log('Icon set generated.');
