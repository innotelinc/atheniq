#!/usr/bin/env node
/**
 * Renders every app-icon asset from one piece of geometry.
 *
 * The AthenIQ mark is the same glyph the site and the console use: an open
 * mortarboard drawn as line art, with a small star above it. Drawing it here
 * once and rendering each size keeps the phone icon, the splash, the Android
 * adaptive layers and the favicon from drifting apart — which is exactly what
 * happened while they were four separate PNGs someone had exported by hand.
 *
 *   node scripts/render-app-icons.mjs
 *
 * Assets land in console/mobile/assets/images. Only sharp is used, and it is
 * already a dependency of this app.
 */
import fs from "node:fs";
import path from "node:path";
import sharp from "sharp";

const HERE = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));
const OUT = path.join(HERE, "..", "mobile", "assets", "images");

/** The glyph, in its own 64×64 space, exactly as the website draws it. */
const GLYPH = `
  <g fill="none" stroke="url(#emerald)" stroke-width="4.6" stroke-linecap="round" stroke-linejoin="round">
    <path d="M32 14 L56 25 L32 36 L8 25 L32 14"/>
    <path d="M22 38 L22 45 L32 50 L42 45 L42 38"/>
    <path d="M56 25 L56 38"/>
  </g>
  <circle cx="56" cy="40.6" r="2.6" fill="#6ee7b7"/>
  <path d="M32 3.6 L34.6 7.3 L32 11 L29.4 7.3 Z" fill="#6ee7b7"/>`;

const EMERALD = `
  <linearGradient id="emerald" x1="0" y1="1" x2="1" y2="0">
    <stop offset="0" stop-color="#059669"/>
    <stop offset="0.55" stop-color="#10b981"/>
    <stop offset="1" stop-color="#34d399"/>
  </linearGradient>`;

/**
 * The glyph's ink is not centred in its 64-unit box (the star sits high, the
 * base sits low), so a plain centre-and-scale leaves the mark visibly low.
 * These are the ink bounds, used to put its optical centre on the canvas centre.
 */
const INK = { left: 5.7, right: 58.3, top: 1.3, bottom: 52.3 };
const INK_CX = (INK.left + INK.right) / 2;
const INK_CY = (INK.top + INK.bottom) / 2;

function placeMark(size, coverage, extra = "") {
  const scale = (size * coverage) / 64;
  return `<g transform="translate(${size / 2} ${size / 2}) scale(${scale}) translate(${-INK_CX} ${-INK_CY})" ${extra}>${GLYPH}</g>`;
}

/** Full-bleed icon: the mark on the app's own near-black, with a soft glow. */
function iconSvg(size) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
  <defs>
    ${EMERALD}
    <radialGradient id="bloom" cx="0.5" cy="0.42" r="0.62">
      <stop offset="0" stop-color="#0f4a3b"/>
      <stop offset="0.55" stop-color="#0a2a24"/>
      <stop offset="1" stop-color="#070f0d"/>
    </radialGradient>
  </defs>
  <rect width="${size}" height="${size}" fill="#070f0d"/>
  <rect width="${size}" height="${size}" fill="url(#bloom)"/>
  ${placeMark(size, 0.58)}
</svg>`;
}

function backgroundSvg(size) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
  <defs>
    <radialGradient id="bloom" cx="0.5" cy="0.46" r="0.7">
      <stop offset="0" stop-color="#0f4a3b"/>
      <stop offset="0.6" stop-color="#092620"/>
      <stop offset="1" stop-color="#070f0d"/>
    </radialGradient>
  </defs>
  <rect width="${size}" height="${size}" fill="url(#bloom)"/>
</svg>`;
}

/** Mark on transparent, for the splash and the Android foreground layer. */
function markSvg(size, coverage, color = null) {
  const stroke = color ? `stroke="${color}"` : 'stroke="url(#emerald)"';
  const glyph = GLYPH
    .replace('stroke="url(#emerald)"', stroke)
    .replace(/#6ee7b7/g, color ?? "#6ee7b7");
  const scale = (size * coverage) / 64;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
  <defs>${EMERALD}</defs>
  <g transform="translate(${size / 2} ${size / 2}) scale(${scale}) translate(${-INK_CX} ${-INK_CY})">${glyph}</g>
</svg>`;
}

async function render(svg, file, { opaque }) {
  let pipeline = sharp(Buffer.from(svg));
  pipeline = opaque
    // App Store icons must not carry an alpha channel, and every surface that
    // shows this one already sits on the app's dark background.
    ? pipeline.flatten({ background: "#070f0d" })
    : pipeline;
  const png = await pipeline.png({ compressionLevel: 9 }).toBuffer();
  fs.writeFileSync(path.join(OUT, file), png);
  const meta = await sharp(png).metadata();
  console.log(`${file.padEnd(28)} ${meta.width}x${meta.height} ${meta.hasAlpha ? "alpha" : "opaque"} ${Math.round(png.length / 1024)} KB`);
}

fs.mkdirSync(OUT, { recursive: true });
fs.writeFileSync(path.join(OUT, "app-icon.svg"), iconSvg(1024));

await render(iconSvg(1024), "icon.png", { opaque: true });
await render(markSvg(1024, 0.72), "splash-icon.png", { opaque: false });
await render(backgroundSvg(1024), "android-icon-background.png", { opaque: true });
// Android crops an adaptive icon, so the mark stays inside the 66% safe circle.
await render(markSvg(1024, 0.5), "android-icon-foreground.png", { opaque: false });
await render(markSvg(1024, 0.56, "#ffffff"), "android-icon-monochrome.png", { opaque: false });
await render(iconSvg(96), "favicon.png", { opaque: true });
