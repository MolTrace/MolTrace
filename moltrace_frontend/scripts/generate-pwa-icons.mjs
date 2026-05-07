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

function cornerHighlightIndices(centers) {
  const indexed = centers.map(([x, y], index) => ({ index, x, y }))
  const topLeft = [...indexed].sort((a, b) => a.x + a.y - (b.x + b.y))[0]?.index
  const topRight = [...indexed].sort((a, b) => b.x - b.y - (a.x - a.y))[0]?.index
  const bottomLeft = [...indexed].sort((a, b) => b.y - b.x - (a.y - a.x))[0]?.index
  const bottomRight = [...indexed].sort((a, b) => b.x + b.y - (a.x + a.y))[0]?.index
  return new Set([topLeft, topRight, bottomLeft, bottomRight].filter((v) => v != null))
}

function buildLogoSvg({ bg }) {
  const R = 5.35
  const pad = 5
  const centers = honeycombCenters(R, pad)
  const highlighted = cornerHighlightIndices(centers)
  const traceBlue = "#42A5F5"
  const honeycombWhite = "#FFFFFF"

  const polys = centers
    .map(([cx, cy], i) => {
      const pts = flatTopHexPoints(cx, cy, R)
      const stroke = highlighted.has(i) ? traceBlue : honeycombWhite
      return `<polygon points="${pts}" fill="none" stroke="${stroke}" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"/>`
    })
    .join("\n")

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect width="64" height="64" fill="${bg}"/>
  <g>${polys}</g>
  <text x="32" y="32" text-anchor="middle" dominant-baseline="central"
    font-family="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    font-weight="900" font-size="20" fill="${traceBlue}">m</text>
</svg>`
}

async function main() {
  const logoBlack = Buffer.from(buildLogoSvg({ bg: "#000000" }), "utf8")
  const logo512 = await sharp(logoBlack).resize(512, 512, { kernel: sharp.kernel.lanczos3 }).png().toBuffer()
  const logo192 = await sharp(logoBlack).resize(192, 192, { kernel: sharp.kernel.lanczos3 }).png().toBuffer()

  const inner = 282
  const logoInner = await sharp(logoBlack).resize(inner, inner, { kernel: sharp.kernel.lanczos3 }).png().toBuffer()

  const maskable512 = await sharp({
    create: {
      width: 512,
      height: 512,
      channels: 4,
      background: { r: 7, g: 11, b: 18, alpha: 1 },
    },
  })
    .composite([{ input: logoInner, gravity: "center" }])
    .png()
    .toBuffer()

  writeFileSync(join(ICONS_DIR, "icon-512.png"), logo512)
  writeFileSync(join(ICONS_DIR, "icon-192.png"), logo192)
  writeFileSync(join(ICONS_DIR, "maskable-icon-512.png"), maskable512)

  writeFileSync(join(ICONS_DIR, "moltrace-mark.svg"), buildLogoSvg({ bg: "#000000" }), "utf8")

  console.log("Wrote MolTrace PWA icons to public/icons/")
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
