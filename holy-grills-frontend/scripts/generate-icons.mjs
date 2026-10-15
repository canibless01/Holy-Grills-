/**
 * generate-icons.mjs — builds the real PNG icon set for the browser tab,
 * installed app, splash and shortcuts.
 *
 * SOURCE OF THE ICON — the brand root logo:
 *   Drop the uploaded wordmark PNG at  public/brand/logo.png  and re-run:
 *     node scripts/generate-icons.mjs
 *   Every icon is then generated from the brand logo (contain-fit onto the
 *   brand bed for favicons; inside the 80% safe zone on cream for maskable
 *   and apple-touch).
 *
 * Without that file the brand flame mark (public/icons/icon.svg) is used as
 * the fallback so the pipeline always produces a complete set.
 *
 * Outputs (public/icons/):
 *   icon-16/32.png            favicon PNGs
 *   icon-192/512.png          manifest "any" icons
 *   apple-touch-icon.png      180×180 (iOS rounds it itself)
 *   maskable-192/512.png      launcher-safe variants
 *
 * Run: node scripts/generate-icons.mjs   (idempotent, committed output)
 */
import sharp from 'sharp';
import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const outDir = path.join(root, 'public', 'icons');
const BRAND_BG = '#FF4E2D';
const CREAM = '#FFF5F0';

const LOGO_FILE = path.join(root, 'public', 'brand', 'logo.png');
const hasBrandLogo = existsSync(LOGO_FILE);

// The brand flame path lifted from public/icons/icon.svg (fallback source).
const { flameDefs, flamePath, corePath } = JSON.parse(
  await readFile(path.join(root, 'scripts', 'icon-flame.json'), 'utf8')
);

/** Rounded-square flame icon (favicon / any-purpose fallback). */
const roundedSvg = () => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  ${flameDefs}
  <rect width="512" height="512" rx="112" fill="${BRAND_BG}"/>
  ${flamePath}
  ${corePath}
</svg>`;

/** Full-bleed flame square (apple-touch / maskable fallback) at artScale. */
const bleedSvg = (artScale) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  ${flameDefs}
  <rect width="512" height="512" fill="${BRAND_BG}"/>
  <g transform="translate(256 256) scale(${artScale}) translate(-256 -256)">
    ${flamePath}
    ${corePath}
  </g>
</svg>`;

/** Brand bed for any-purpose logo icons (rounded square, transparent centre). */
const logoBedSvg = () => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <rect width="512" height="512" rx="112" fill="${BRAND_BG}"/>
</svg>`;

/** Cream bed for apple-touch / maskable logo icons. */
const logoCreamSvg = () => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <rect width="512" height="512" fill="${CREAM}"/>
</svg>`;

const transparent = { r: 0, g: 0, b: 0, alpha: 0 };

/** contain-fit the logo into `size`, composited over `bedSvg`'s PNG. */
const writeLogoIcon = async (size, bedSvg, file, logoBox = size) => {
  const logo = await sharp(LOGO_FILE).resize(logoBox, logoBox, { fit: 'contain', background: transparent }).png().toBuffer();
  await sharp(Buffer.from(bedSvg()))
    .composite([{ input: logo }])
    .resize(size, size)
    .png()
    .toFile(path.join(outDir, file));
  console.log('✓', file, '(brand logo)');
};

const writeFlamePng = async (svg, file, size) => {
  await sharp(Buffer.from(svg)).resize(size, size).png().toFile(path.join(outDir, file));
  console.log('✓', file);
};

if (hasBrandLogo) {
  await writeLogoIcon(512, logoBedSvg, 'icon-512.png', 420);
  await writeLogoIcon(192, logoBedSvg, 'icon-192.png', 164);
  await writeLogoIcon(32, logoBedSvg, 'icon-32.png', 30);
  await writeLogoIcon(16, logoBedSvg, 'icon-16.png', 16);
  // iOS — full cream bed, logo at ~84% (iOS applies its own corner mask)
  await writeLogoIcon(180, logoCreamSvg, 'apple-touch-icon.png', 152);
  // Android maskable — artwork inside the 80% safe zone
  await writeLogoIcon(512, logoCreamSvg, 'maskable-512.png', 410);
  await writeLogoIcon(192, logoCreamSvg, 'maskable-192.png', 164);
  console.log('Icon set generated FROM THE BRAND LOGO.');
} else {
  // Flame fallback
  await writeFlamePng(roundedSvg(), 'icon-192.png', 192);
  await writeFlamePng(roundedSvg(), 'icon-512.png', 512);
  await writeFlamePng(roundedSvg(), 'icon-32.png', 32);
  await writeFlamePng(roundedSvg(), 'icon-16.png', 16);
  await writeFlamePng(bleedSvg(1), 'apple-touch-icon.png', 180);
  await writeFlamePng(bleedSvg(0.62), 'maskable-192.png', 192);
  await writeFlamePng(bleedSvg(0.62), 'maskable-512.png', 512);
  console.log('Icon set generated from the flame fallback (no public/brand/logo.png found).');
}
