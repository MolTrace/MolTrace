/**
 * Derives the two dimensional-mark assets from scripts/assets/moltrace-mark-3d-source.png.
 *
 * The source is the 3D render, downsized to 1024px — every derived asset is 512px
 * or smaller, so the full-resolution original buys nothing but repository weight.
 * Replace that file and re-run this script when the render changes.
 *
 * Run: node scripts/generate-3d-mark-assets.mjs
 *
 * WHY TWO ASSETS AND NOT ONE RESIZE. The same render cannot serve both surfaces,
 * and finding that out cost several wrong attempts worth recording:
 *
 *   THE SHARE CARD gets a cut-out mark. It sits at 210px on the card's own dark
 *   gradient, so the render's square backdrop has to disappear — matching the two
 *   navies does not work, because the render carries a vignette and a flat fill
 *   cannot track a gradient at every point. The art is glow on near-black, so
 *   luminance is opacity: alpha comes from the greyscale channel under a contrast
 *   curve, which keeps the bloom's falloff where a hard threshold would cut a
 *   halo ring.
 *
 *   SITE CHROME gets a tile, with the render untouched. The cut-out is wrong here
 *   for a reason that only shows up small: the alpha it derives leaves the dark
 *   facets TRANSPARENT. At 210px on a dark gradient that is invisible and
 *   correct. At 32px it means the hexagon body is not there — only the bright "m"
 *   and the rim are opaque, so the mark reads as a letter floating in a haze, and
 *   on the light header it collapses into a grey smudge.
 *
 * WHAT DID NOT WORK, so nobody repeats it: reconstructing a solid body by filling
 * the hexagon interior — first by span-filling each row, then by flood-filling
 * from the frame border. Both recovered roughly the right region, and both still
 * looked like haze, because this render has no hard silhouette to mask to. Its
 * edge is a soft luminous falloff. Masking a soft edge gives you a soft edge.
 *
 * The tile solves it by not fighting the render at all: a rounded dark square IS
 * a hard silhouette, it is self-contained so it reads on a light or a dark
 * header, and the art inside is exactly what was authored. This is what app icons
 * have always done with luminous artwork, and it is why the call sites already
 * asked for `rounded-xl`.
 *
 * The favicons are NOT built here — see generate-pwa-icons.mjs. They keep the
 * drawn SVG mark, because a favicon is sized in device pixels and at 16 of them
 * this render has no legible letter.
 */

import sharp from "sharp"
import { writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..")
const SOURCE = join(ROOT, "scripts", "assets", "moltrace-mark-3d-source.png")
const ICONS = join(ROOT, "public", "icons")

/**
 * The share-card mark: background removed, bloom preserved.
 *
 * 420px is a true 2× of the card's 210px slot. Palette quantisation is safe on a
 * narrow blue ramp, and it matters because the edge runtime fetches this on every
 * card render — it takes the file from ~450KB to ~80KB with no visible change.
 */
async function buildCardMark() {
  const S = 420
  const base = sharp(SOURCE).resize(S, S, { fit: "inside" })
  const rgb = await base.clone().removeAlpha().toBuffer()
  const alpha = await base.clone().greyscale().linear(2.4, -12).toBuffer()
  // Write the encoded buffer, never sharp(buf).toFile() — that re-encodes under
  // default options and silently discards the palette, which once landed this
  // file 68% over what the buffer had measured.
  return sharp(rgb)
    .joinChannel(alpha)
    .png({ compressionLevel: 9, palette: true, quality: 92 })
    .toBuffer()
}

/**
 * The site-chrome tile: the render as authored, on a rounded dark square.
 *
 * 128px covers the largest use (`h-10`, 40px) on a 3× display. The corner radius
 * is 24% of the side — the proportion iOS and Android use, and the one that reads
 * as "app icon" rather than "photo with rounded corners".
 */
async function buildChromeTile() {
  const N = 128
  const face = await sharp(SOURCE).resize(N, N, { fit: "cover" }).removeAlpha().toBuffer()
  const r = Math.round(N * 0.24)
  const rounded = Buffer.from(
    `<svg width="${N}" height="${N}"><rect width="${N}" height="${N}" rx="${r}" ry="${r}" fill="#fff"/></svg>`,
  )
  return sharp(face)
    .composite([{ input: rounded, blend: "dest-in" }])
    .png({ compressionLevel: 9 })
    .toBuffer()
}

const outputs = [
  ["moltrace-mark-3d-512.png", await buildCardMark()],
  ["moltrace-mark-3d-tile-128.png", await buildChromeTile()],
]
for (const [name, data] of outputs) {
  writeFileSync(join(ICONS, name), data)
  console.log(`  ${name}  ${data.length} bytes`)
}
