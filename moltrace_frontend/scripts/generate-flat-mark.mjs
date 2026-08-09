import sharp from "sharp"
import { readFileSync, writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

/**
 * Rasterise the flat MolTrace mark for the social card.
 *
 * The SVG is the source of truth; this only exists because next/og cannot render
 * it. Two attempts at inlining the vector failed — base64 threw
 * InvalidCharacterError (btoa is Latin-1 only, and the file has em-dashes in its
 * comments), and a percent-encoded data URI then hung the route outright, since
 * Satori's SVG support does not cover this drawing.
 *
 * So: edit moltrace-mark-flat.svg, run `pnpm generate:flat-mark`, commit both.
 * Editing the PNG directly leaves the two out of sync with nothing to catch it.
 *
 *   pnpm generate:flat-mark
 */
const here = dirname(fileURLToPath(import.meta.url))
const icons = join(here, "..", "public", "icons")
const src = join(icons, "moltrace-mark-flat.svg")
const out = join(icons, "moltrace-mark-flat-512.png")

// High density so the hexagon's 2.6px stroke stays clean at 512, then contain so
// the mark keeps its aspect and the card can place it without distortion.
const png = await sharp(readFileSync(src), { density: 1200 })
  .resize(512, 512, { fit: "contain", background: { r: 0, g: 0, b: 0, alpha: 0 } })
  .png()
  .toBuffer()

writeFileSync(out, png)
console.log(`generate-flat-mark: wrote ${out} (${png.length} bytes)`)
