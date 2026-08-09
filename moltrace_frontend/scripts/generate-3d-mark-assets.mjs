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
 *   SITE CHROME gets the render cut to a CONSTRUCTED hexagon. The share card's
 *   cut-out is wrong here for a reason that only shows up small: the alpha it
 *   derives leaves the dark facets TRANSPARENT. At 210px on a dark gradient that
 *   is invisible and correct. At 32px the hexagon body is not there — only the
 *   bright "m" and the rim are opaque, so the mark reads as a letter floating in
 *   a haze, and on the light header it collapses into a grey smudge. The fix is
 *   a silhouette the render does not have; see buildChromeMark for how it is
 *   fitted and checked.
 *
 * A ROUNDED DARK TILE ALSO WORKS, AND IS WRONG. It shipped briefly, and it is the
 * obvious answer — a tile is self-contained, so it reads on a light or a dark
 * header without knowing which. But it puts a dark square around the mark on a
 * white header, which is the thing the cut-out exists to remove. Do not bring it
 * back as a simplification.
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
 * The site-chrome mark: the render cut to a hexagon, no backdrop.
 *
 * 128px covers the largest use (`h-10`, 40px) on a 3× display.
 *
 * THE SILHOUETTE IS COMPUTED, NOT DETECTED, and that is the whole trick. Four
 * attempts to find this render's outline from its own pixels all failed, and they
 * failed the same way, so they are worth naming rather than rediscovering:
 *
 *   - Alpha from luminance (what the share card uses) leaves the dark facets
 *     transparent. Right at 210px on a dark gradient; at 32px the hexagon body is
 *     simply absent and only the "m" and the rim survive.
 *   - Span-filling each row, and flood-filling from the frame border, both
 *     recovered roughly the right region and both still looked like haze — the
 *     alpha edge they produce is a soft ramp, and a soft dark ramp on a white
 *     header is a smudge.
 *   - Flood-filling with a hard threshold and no glow latched onto the floor the
 *     object is lit against, not the object, and cut a grey slab.
 *
 * The common cause: this render has no hard silhouette to find. It is a lit
 * object on a surface with atmospheric spill, and every boundary in it is a
 * gradient. Detection cannot succeed on an image with nothing to detect.
 *
 * So the hexagon is constructed instead. A pointy-top hexagon has height 2R and
 * width R√3; fitting R to the art's measured height predicts a width within 4% of
 * the measured one, which is the check that the render really is that shape — if
 * a future render is not, that number moves and this fails loudly here rather
 * than quietly in the output. Masking to it gives the hard edge the pixels never
 * had, so the mark reads as a dark hexagon with a lit rim: high contrast on a
 * white header, and no dark square around it.
 */
async function buildChromeMark(N = 128) {
  const S = 512
  // Materialise the resize before extracting — chaining resize().extract()
  // computes the crop against the pre-resize geometry and throws.
  const frame = await sharp(SOURCE).resize(S, S, { fit: "inside" }).png().toBuffer()
  const { width, height } = await sharp(frame).metadata()

  // Bounding box of the lit art, so the geometry follows the render rather than
  // hard-coded numbers a re-render would silently invalidate.
  const lum = await sharp(frame).greyscale().raw().toBuffer()
  let x0 = Infinity, y0 = Infinity, x1 = -1, y1 = -1
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (lum[y * width + x] > 60) {
        if (x < x0) x0 = x
        if (x > x1) x1 = x
        if (y < y0) y0 = y
        if (y > y1) y1 = y
      }
    }
  }
  const cx = (x0 + x1) / 2
  const cy = (y0 + y1) / 2
  const R = (y1 - y0 + 1) / 2

  const predictedWidth = R * Math.sqrt(3)
  const match = (x1 - x0 + 1) / predictedWidth
  if (match < 0.9 || match > 1.1) {
    throw new Error(
      `Source is not the expected pointy-top hexagon: height implies a width of ` +
        `${predictedWidth.toFixed(0)}px but the art measures ${x1 - x0 + 1}px ` +
        `(${(match * 100).toFixed(0)}%). Re-fit the mask before shipping this.`,
    )
  }

  const points = Array.from({ length: 6 }, (_, i) => {
    const angle = Math.PI / 2 + (i * Math.PI) / 3
    return `${(cx + R * Math.cos(angle)).toFixed(1)},${(cy + R * Math.sin(angle)).toFixed(1)}`
  }).join(" ")
  const hexagon = Buffer.from(
    `<svg width="${width}" height="${height}"><polygon points="${points}" fill="#fff"/></svg>`,
  )

  // ensureAlpha, NOT removeAlpha. `dest-in` writes into the destination's alpha
  // channel, so on a 3-channel image it silently does nothing and you ship the
  // full opaque square — which is exactly the dark box this mask exists to
  // remove, and it survives a casual look because the corners are near-black
  // anyway.
  const cut = await sharp(frame)
    .ensureAlpha()
    .composite([{ input: hexagon, blend: "dest-in" }])
    .png()
    .toBuffer()

  // Crop to the hexagon with a little air, then lift so the neon carries small.
  const side = Math.round(2 * R * 1.04)
  const left = Math.max(0, Math.min(width - side, Math.round(cx - side / 2)))
  const top = Math.max(0, Math.min(height - side, Math.round(cy - side / 2)))
  return sharp(cut)
    .extract({ left, top, width: side, height: side })
    .resize(N, N)
    .linear(1.3, -3)
    .png({ compressionLevel: 9 })
    .toBuffer()
}

const outputs = [
  ["moltrace-mark-3d-512.png", await buildCardMark()],
  ["moltrace-mark-3d-hex-128.png", await buildChromeMark()],
  // The large hex is for display sizes — the docs site's 400px splash hero. It
  // is a separate file rather than one asset for both because the 128 is fetched
  // in the header of every page, and shipping a 512 there to serve a 32px slot
  // would be ~5x the bytes on the hot path to help two pages.
  ["moltrace-mark-3d-hex-512.png", await buildChromeMark(512)],
]
for (const [name, data] of outputs) {
  writeFileSync(join(ICONS, name), data)
  console.log(`  ${name}  ${data.length} bytes`)
}
