/**
 * Rasterizes the MolTrace mark (matches components/branding/molecule-logo-mark.tsx)
 * into public/icons/*.png for PWA / favicons.
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
/** Honeycomb stroke color. */
const HONEYCOMB_BRIGHT_BLUE = "#26C6FF"
const MARK_FILL = "#FFFFFF"
const WORDMARK_FILL = "#111827"

/** Flat-top hex in 64x64 viewBox - matches `LOGO_HEX_CLIP` in molecule-logo-mark.tsx */
const LOGO_HEX_POLYGON_POINTS = "16,0 48,0 64,32 48,64 16,64 0,32"

const SQRT3 = Math.sqrt(3)

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

function honeycombCenters(R, pad) {
  const dx = SQRT3 * R
  const dy = 1.5 * R
  const centers = []
  for (let row = -2; ; row++) {
    const cy = pad + row * dy
    if (cy > 64 + R) break
    const ox = (row % 2) * (dx / 2)
    for (let col = -2; ; col++) {
      const cx = pad + ox + col * dx
      if (cx > 64 + R) break
      centers.push([cx, cy])
    }
  }
  return centers
}

function buildLogoMarkSvg() {
  const R = 5.35
  const pad = 5
  const centers = honeycombCenters(R, pad)

  const polys = centers
    .map(([cx, cy]) => {
      const pts = flatTopHexPoints(cx, cy, R)
      return `<polygon points="${pts}"/>`
    })
    .join("\n")

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64" fill="none" role="img" aria-labelledby="moltrace-mark-title">
  <title id="moltrace-mark-title">MolTrace logo</title>
  <defs>
    <clipPath id="moltrace-mark-hex" clipPathUnits="userSpaceOnUse">
      <polygon points="${LOGO_HEX_POLYGON_POINTS}"/>
    </clipPath>
  </defs>
  <g clip-path="url(#moltrace-mark-hex)">
    <rect width="64" height="64" fill="${LOGO_BACKGROUND_DARK_BLUE}"/>
    <g fill="none" stroke="${HONEYCOMB_BRIGHT_BLUE}" stroke-width="2" stroke-linecap="butt" stroke-linejoin="miter" shape-rendering="geometricPrecision">
${polys}
    </g>
    <g
      font-family="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
      font-size="36"
      font-weight="900"
      text-anchor="middle"
      text-rendering="geometricPrecision"
    >
      <text x="32" y="31.2" dy="0.33em" fill="none" stroke="${LOGO_BACKGROUND_DARK_BLUE}" stroke-width="0" stroke-linecap="round" stroke-linejoin="round" paint-order="stroke">m</text>
      <text x="32" y="31.2" dy="0.33em" fill="${MARK_FILL}">m</text>
    </g>
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

  writeFileSync(join(PUBLIC_DIR, "icon.svg"), logoSvg, "utf8")
  writeFileSync(join(ICONS_DIR, "moltrace-mark.svg"), logoSvg, "utf8")
  writeFileSync(join(ICONS_DIR, "moltrace-wordmark.svg"), wordmarkSvg, "utf8")

  console.log("Wrote MolTrace PWA icons to public/icons/")
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
