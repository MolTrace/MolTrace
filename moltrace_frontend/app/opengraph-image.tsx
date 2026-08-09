import { ImageResponse } from "next/og"

import { SITE_NAME } from "@/lib/seo/site"

// Default social-share card (1200×630) inherited by every route that doesn't
// define its own opengraph-image. Rendered at the edge with next/og.
export const runtime = "edge"
export const alt = `${SITE_NAME} — audit-ready evidence for pharmaceutical R&D`
export const size = { width: 1200, height: 630 }
export const contentType = "image/png"

/**
 * TWO THINGS THIS CARD GOT WRONG, both visible the moment a link was shared.
 *
 * 1. THE LOGO WAS NOT THE LOGO. It was a generated gradient square containing the
 *    letter "M" — a stand-in that shipped. The real mark exists as
 *    public/icons/icon-512.png and is what every other surface uses, so the one
 *    place a stranger meets the brand first was the one place not using it.
 *
 * 2. THE COMPOSITION DID NOT SURVIVE CROPPING. Content sat in three bands with
 *    `space-between` — mark top-left, a 68px headline across the middle, domain
 *    bottom-left. Chat clients preview a 1200×630 card as a small near-square
 *    thumbnail, and cropping that layout gave a slab of headline sliced
 *    mid-word ("…dit-ready evidence for pharmaceutical R…") with no mark in
 *    frame at all.
 *
 * So the mark and wordmark are now centred and large, and the supporting copy is
 * short enough to survive being cut. A centre-weighted composition is the one
 * that degrades best across clients that crop differently: whatever a platform
 * keeps, it keeps the brand.
 */
export default async function OpengraphImage() {
  // The dimensional mark.
  //
  // I briefly swapped this for a flat variant on the reasoning that bloom, bevel
  // and a gradient "m" would turn to mush once a chat client scaled the card to a
  // thumbnail. That was an assertion, not a measurement, and it did not survive
  // being checked: rendered at 120px and 200px — the widths a compact preview
  // actually uses — the two are indistinguishable, and at 360px the dimensional
  // one is richer. Swapping it also made this the only surface in the product not
  // using the brand mark, which is a real cost paid for an imagined benefit.
  //
  // HOW moltrace-mark-3d-512.png WAS DERIVED, because the master render is not in
  // this repo and the step is not obvious. The master arrives as RGB with NO alpha
  // channel — the mark floats on its own near-black square. Dropping that straight
  // onto the card left a visible seam: the square stayed distinguishable from the
  // gradient behind it however carefully the two navies were matched, because the
  // master carries a subtle vignette (corners rgb(0,7,19), mid-edges rgb(0,12,29))
  // and a flat backdrop cannot match a gradient at every point.
  //
  // Since the art is glow-on-near-black, luminance IS opacity. So alpha is derived
  // from the greyscale channel with a contrast curve, which drops the backdrop to
  // fully transparent while keeping the bloom's falloff intact — a hard threshold
  // would have cut a halo ring around the glow:
  //
  //   const base = sharp(master).resize(420, 420, { fit: "inside" })
  //   const rgb   = await base.clone().removeAlpha().toBuffer()
  //   const alpha = await base.clone().greyscale().linear(2.4, -12).toBuffer()
  //   const out = await sharp(rgb).joinChannel(alpha)
  //     .png({ compressionLevel: 9, palette: true }).toBuffer()
  //   writeFileSync(dest, out)   // NOT sharp(out).toFile(dest) — see below
  //
  // 420px is a true 2× of the 210px slot, and palette quantisation is safe on a
  // narrow blue ramp — together they took the asset from 454KB to 81KB with no
  // visible difference in the rendered card, which matters because the edge
  // runtime fetches this file on every render.
  //
  // Write the encoded buffer directly. Handing it back to `sharp(buf).toFile()`
  // re-encodes it under default options and silently discards the palette, which
  // is how this first landed at 136KB — 68% over what the buffer had measured.
  //
  // Fetched relative to this module so it works in the edge runtime, where there
  // is no filesystem.
  const mark = await fetch(new URL("../public/icons/moltrace-mark-3d-512.png", import.meta.url)).then(
    (res) => res.arrayBuffer(),
  )

  return new ImageResponse(
    (
      <div
        style={{
          height: "100%",
          width: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "34px",
          background:
            "radial-gradient(120% 120% at 50% 0%, #0d1a2b 0%, #070b12 55%, #05070c 100%)",
          fontFamily: "sans-serif",
          padding: "64px",
        }}
      >
        {/* Mark ABOVE the wordmark, not beside it. Side by side, the block sits
            around x=335..855, so a client that crops to the right-hand square
            loses the mark completely. Stacked, the mark sits on the horizontal
            centre line and survives a left, centre or right crop alike — which
            is the whole point of the change. */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "18px" }}>
          {/* A plain <img>: next/og renders to a raster, so next/image has no
              meaning inside an ImageResponse. */}
          <img src={mark as unknown as string} width={210} height={210} alt="" />
          <div style={{ fontSize: "86px", fontWeight: 800, color: "#f4f9fc", letterSpacing: "-0.02em" }}>
            {SITE_NAME}
          </div>
        </div>

        {/* Short by design. The previous 68px headline was the thing that got
            sliced mid-word in every small preview. */}
        <div
          style={{
            fontSize: "38px",
            fontWeight: 500,
            color: "#7dd3e8",
            textAlign: "center",
            maxWidth: "900px",
            lineHeight: 1.25,
          }}
        >
          Audit-ready evidence for pharmaceutical R&amp;D
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "14px", fontSize: "28px", color: "#9fb3c2" }}>
          <div style={{ width: "12px", height: "12px", borderRadius: "50%", background: "#a78bfa" }} />
          moltrace.co
        </div>
      </div>
    ),
    { ...size },
  )
}
