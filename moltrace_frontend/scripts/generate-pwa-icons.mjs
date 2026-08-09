/**
 * Rasterizes the drawn MolTrace mark into public/icons/*.png for PWA / favicons.
 *
 * THIS DRAWING IS NO LONGER A MIRROR OF molecule-logo-mark.tsx, and the old note
 * here — "change one and you must change the other" — no longer applies. Site
 * chrome now uses the dimensional render; favicons keep this drawing, because
 * they are the one surface where the render fails. A favicon is specified in
 * DEVICE pixels, so 16 means 16 with no retina multiplier, and at that size the
 * render measures a grey smudge with no legible letter while this drawing stays
 * crisp. The reasoning and the measurements are in molecule-logo-mark.tsx.
 *
 * So: this file owns the favicon, the .ico, the Apple icons and the PWA tiles,
 * and it is self-contained. It is not drift, and it is not stale — do not
 * "resync" it to the component.
 *
 * Run: node scripts/generate-pwa-icons.mjs
 */

import sharp from "sharp"
import { writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const PUBLIC_DIR = join(__dirname, "..", "public")
const ICONS_DIR = join(__dirname, "..", "public", "icons")

/** Matches `molecule-logo-mark.tsx` */
const LOGO_BACKGROUND_DARK_BLUE = "#051f3a"
/** Honeycomb + trace-line stroke — the "Trace" cyan from the wordmark. */
const HONEYCOMB_BRIGHT_BLUE = "#26C6FF"
/** The neon tube's hot core, where the cyan blows out toward white. */
const NEON_CORE_WHITE = "#CDF0FF"
/** The prism's far edge, catching light at a glancing angle. */
const PRISM_SHELL_BLUE = "#7FD8FF"
/** Rim light along the raised m. */
const M_RIM_LIGHT = "#8FDCFF"
/** The m's lit face, cooling from white at the top to a pale steel below. */
const M_FACE_TOP = "#FFFFFF"
const M_FACE_BOTTOM = "#B9D8EC"
/** The shadow the raised m casts onto the prism floor. */
const M_CAST_SHADOW = "#020C17"
const WORDMARK_FILL = "#111827"

/** Room left around the hexagon for the bloom, in viewBox units. */
const HEX_GLOW_INSET = 3.5

function flatTopHexPoints(cx, cy, R) {
  const pts = []
  for (let i = 0; i < 6; i++) {
    const ang = Math.PI / 6 + (i * Math.PI) / 3
    const x = cx + R * Math.cos(ang)
    const y = cy + R * Math.sin(ang)
    pts.push(`${x.toFixed(3)},${y.toFixed(3)}`)
  }
  return pts.join(" ")
}

/** The mark's outer hexagon, inset so the neon bloom has somewhere to fall. */
function markHexPoints(inset) {
  const r = 32 - inset
  const h = r / 2
  return [
    `${32 - h},${32 - r}`,
    `${32 + h},${32 - r}`,
    `${32 + r},32`,
    `${32 + h},${32 + r}`,
    `${32 - h},${32 + r}`,
    `${32 - r},32`,
  ].join(" ")
}

const HEX_OUTER_POINTS = markHexPoints(HEX_GLOW_INSET)

function buildLogoMarkSvg() {
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64" fill="none" role="img" aria-labelledby="moltrace-mark-title">
  <title id="moltrace-mark-title">MolTrace logo</title>
  <defs>
    <clipPath id="moltrace-mark-hex" clipPathUnits="userSpaceOnUse">
      <polygon points="${HEX_OUTER_POINTS}"/>
    </clipPath>
    <mask id="moltrace-mark-cutout" maskUnits="userSpaceOnUse" x="0" y="0" width="64" height="64">
      <rect width="64" height="64" fill="#fff"/>
      <text x="32" y="32" dy="0.33em"
        font-family="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
        font-size="34" font-weight="900" text-anchor="middle"
        text-rendering="geometricPrecision" fill="#000" stroke="#000" stroke-width="1.5">m</text>
    </mask>
    <filter id="moltrace-mark-glow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur in="SourceGraphic" stdDeviation="1.1" result="blur"/>
      <feFlood flood-color="${HONEYCOMB_BRIGHT_BLUE}" flood-opacity="0.85" result="flood"/>
      <feComposite in="flood" in2="blur" operator="in" result="coloredBlur"/>
      <feMerge>
        <feMergeNode in="coloredBlur"/>
        <feMergeNode in="coloredBlur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
    <filter id="moltrace-mark-bloom" x="-75%" y="-75%" width="250%" height="250%">
      <feGaussianBlur in="SourceGraphic" stdDeviation="2.6" result="wide"/>
      <feFlood flood-color="${HONEYCOMB_BRIGHT_BLUE}" flood-opacity="0.9" result="flood"/>
      <feComposite in="flood" in2="wide" operator="in" result="coloredBlur"/>
      <feMerge>
        <feMergeNode in="coloredBlur"/>
        <feMergeNode in="coloredBlur"/>
      </feMerge>
    </filter>
    <filter id="moltrace-mark-cast" x="-40%" y="-40%" width="180%" height="180%">
      <feDropShadow dx="0.9" dy="1.3" stdDeviation="0.9" flood-color="${M_CAST_SHADOW}" flood-opacity="0.85"/>
    </filter>
    <linearGradient id="moltrace-mark-mface" x1="0" y1="0" x2="0.25" y2="1">
      <stop offset="0%" stop-color="${M_FACE_TOP}"/>
      <stop offset="55%" stop-color="${M_FACE_TOP}"/>
      <stop offset="100%" stop-color="${M_FACE_BOTTOM}"/>
    </linearGradient>
    <linearGradient id="moltrace-mark-topface" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#14425F"/>
      <stop offset="100%" stop-color="#0A2A45"/>
    </linearGradient>
    <linearGradient id="moltrace-mark-rightface" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#0F3552"/>
      <stop offset="100%" stop-color="#061C2E"/>
    </linearGradient>
    <linearGradient id="moltrace-mark-leftface" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#0A2438"/>
      <stop offset="100%" stop-color="#03101E"/>
    </linearGradient>
  </defs>
  <polygon points="${HEX_OUTER_POINTS}" fill="none" stroke="${HONEYCOMB_BRIGHT_BLUE}" stroke-width="2.4" stroke-linejoin="miter" filter="url(#moltrace-mark-bloom)" opacity="0.75"/>
  <g clip-path="url(#moltrace-mark-hex)">
    <rect width="64" height="64" fill="${LOGO_BACKGROUND_DARK_BLUE}"/>
    <g mask="url(#moltrace-mark-cutout)">
      <polygon points="16,0 48,0 32,32 0,32" fill="url(#moltrace-mark-topface)"/>
      <polygon points="48,0 64,32 48,64 32,32" fill="url(#moltrace-mark-rightface)"/>
      <polygon points="32,32 48,64 16,64 0,32" fill="url(#moltrace-mark-leftface)"/>
    </g>
    <g mask="url(#moltrace-mark-cutout)" filter="url(#moltrace-mark-glow)" stroke-width="1.1" stroke-linejoin="miter" stroke-linecap="butt" fill="none">
      <g transform="translate(24 14) matrix(1 0 -0.5 1 0 0) translate(-24 -14)">
        <polygon points="${flatTopHexPoints(24, 14, 4)}" stroke="${HONEYCOMB_BRIGHT_BLUE}"/>
      </g>
      <g transform="translate(52 23) matrix(0.5 1 -0.5 1 0 0) translate(-52 -23)">
        <polygon points="${flatTopHexPoints(52, 23, 4)}" stroke="${HONEYCOMB_BRIGHT_BLUE}"/>
      </g>
      <g transform="translate(27 53) matrix(1 0 0.5 1 0 0) translate(-27 -53)">
        <polygon points="${flatTopHexPoints(27, 53, 4)}" stroke="${HONEYCOMB_BRIGHT_BLUE}"/>
      </g>
    </g>
    <g mask="url(#moltrace-mark-cutout)" filter="url(#moltrace-mark-glow)" stroke="${HONEYCOMB_BRIGHT_BLUE}" stroke-width="1.3" stroke-linecap="round" fill="none">
      <line x1="32" y1="32" x2="48" y2="0"/>
      <line x1="32" y1="32" x2="48" y2="64"/>
      <line x1="32" y1="32" x2="0" y2="32"/>
    </g>
  </g>
  <polygon points="${markHexPoints(HEX_GLOW_INSET - 1.15)}" fill="none" stroke="${PRISM_SHELL_BLUE}" stroke-width="0.7" stroke-linejoin="miter" opacity="0.4"/>
  <polygon points="${HEX_OUTER_POINTS}" fill="none" stroke="${HONEYCOMB_BRIGHT_BLUE}" stroke-width="2.3" stroke-linejoin="miter"/>
  <polygon points="${HEX_OUTER_POINTS}" fill="none" stroke="${NEON_CORE_WHITE}" stroke-width="0.85" stroke-linejoin="miter" opacity="0.9"/>
  <g
    font-family="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    font-size="34"
    font-weight="900"
    text-anchor="middle"
    text-rendering="geometricPrecision"
  >
    <text x="32" y="32" dy="0.33em" fill="url(#moltrace-mark-mface)" filter="url(#moltrace-mark-cast)">m</text>
    <text x="32" y="32" dy="0.33em" fill="none" stroke="${M_RIM_LIGHT}" stroke-width="0.9" stroke-linejoin="round" opacity="0.95">m</text>
  </g>
</svg>`
}

function buildWordmarkSvg() {
  const mark = buildLogoMarkSvg()
    .replace(/<\?xml version="1\.0" encoding="UTF-8"\?>\n/, "")
    .replace(/<svg[^>]*>/, '<svg x="0" y="0" width="64" height="64" viewBox="0 0 64 64" fill="none" aria-hidden="true">')
    .replace(/ role="img" aria-labelledby="moltrace-mark-title"/, "")
    .replace(/moltrace-mark-hex/g, "moltrace-wordmark-mark-hex")
    .replace(/\s*<title[^>]*>MolTrace logo<\/title>\n/, "\n")

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="320" height="80" viewBox="0 0 320 80" fill="none" role="img" aria-labelledby="moltrace-wordmark-title">
  <title id="moltrace-wordmark-title">MolTrace</title>
  <g transform="translate(8 8)">
    ${mark}
  </g>
  <text
    x="88"
    y="49"
    font-family="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    font-size="32"
    font-weight="700"
    letter-spacing="0"
    text-rendering="geometricPrecision"
  ><tspan fill="${WORDMARK_FILL}">Mol</tspan><tspan fill="${HONEYCOMB_BRIGHT_BLUE}" font-weight="800">Trace</tspan></text>
</svg>`
}

async function main() {
  const logoSvg = buildLogoMarkSvg()
  const wordmarkSvg = buildWordmarkSvg()
  const logoRgb = Buffer.from(logoSvg, "utf8")
  const logo512 = await sharp(logoRgb).resize(512, 512, { kernel: sharp.kernel.lanczos3 }).png().toBuffer()
  const logo192 = await sharp(logoRgb).resize(192, 192, { kernel: sharp.kernel.lanczos3 }).png().toBuffer()

  const inner = 282
  const logoInner = await sharp(logoRgb).resize(inner, inner, { kernel: sharp.kernel.lanczos3 }).png().toBuffer()

  const maskable512 = await sharp({
    create: {
      width: 512,
      height: 512,
      channels: 4,
      background: { r: 5, g: 31, b: 58, alpha: 1 },
    },
  })
    .composite([{ input: logoInner, gravity: "center" }])
    .png()
    .toBuffer()

  writeFileSync(join(ICONS_DIR, "icon-512.png"), logo512)
  writeFileSync(join(ICONS_DIR, "icon-192.png"), logo192)
  writeFileSync(join(ICONS_DIR, "maskable-icon-512.png"), maskable512)
  writeFileSync(join(PUBLIC_DIR, "apple-icon.png"), logo192)

  writeFileSync(join(PUBLIC_DIR, "icon.svg"), logoSvg, "utf8")
  writeFileSync(join(ICONS_DIR, "moltrace-mark.svg"), logoSvg, "utf8")
  writeFileSync(join(ICONS_DIR, "moltrace-wordmark.svg"), wordmarkSvg, "utf8")

  console.log("Wrote MolTrace PWA icons to public/icons/")
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
