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
const ICONS_DIR = join(__dirname, "..", "public", "icons")

/** Matches `molecule-logo-mark.tsx` */
const LOGO_BACKGROUND_DARK_BLUE = "#051f3a"
/**  */
const HEX_STROKE = "#26C6FF"
const HEX_STROKE_WIDTH = "2"
const MARK_FILL = "#FFFFFF"

/** Flat-top hex in 64×64 viewBox — matches `LOGO_HEX_CLIP` in molecule-logo-mark.tsx */
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
  for (let row = 0; ; row++) {
    const cy = pad + row * dy
    if (cy > 64 - pad - R * 0.35) break
    const ox = (row % 2) * (dx / 2)
    for (let col = 0; ; col++) {
      const cx = pad + ox + col * dx
      if (cx > 64 - pad - R * 0.35) break
      centers.push([cx, cy])
    }
  }
  return centers
}

function buildLogoSvg({ bg }) {
  const R = 5.35
  const pad = 5
  const centers = honeycombCenters(R, pad)

  const polys = centers
    .map(([cx, cy]) => {
      const pts = flatTopHexPoints(cx, cy, R)
      return `<polygon points="${pts}" fill="none" stroke="${HEX_STROKE}" stroke-width="${HEX_STROKE_WIDTH}" stroke-linecap="butt" stroke-linejoin="miter"/>`
    })
    .join("\n")

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <defs>
    <clipPath id="moltrace-logo-hex"><polygon points="${LOGO_HEX_POLYGON_POINTS}"/></clipPath>
  </defs>
  <g clip-path="url(#moltrace-logo-hex)">
    <rect width="64" height="64" fill="${bg}"/>
    <g>${polys}</g>
    <text x="31.5" y="32" text-anchor="middle" dominant-baseline="central"
      font-family="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
      font-weight="900" font-size="20" fill="${MARK_FILL}">m</text>
  </g>
</svg>`
}

async function main() {
  const logoRgb = Buffer.from(buildLogoSvg({ bg: LOGO_BACKGROUND_DARK_BLUE }), "utf8")
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

  writeFileSync(join(ICONS_DIR, "moltrace-mark.svg"), buildLogoSvg({ bg: LOGO_BACKGROUND_DARK_BLUE }), "utf8")

  console.log("Wrote MolTrace PWA icons to public/icons/")
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
