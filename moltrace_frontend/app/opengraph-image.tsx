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
  // Fetched relative to this module so it works in the edge runtime, where there
  // is no filesystem. 512px source rendered at 190 — sharp on a 2× display.
  const mark = await fetch(new URL("../public/icons/icon-512.png", import.meta.url)).then((res) =>
    res.arrayBuffer(),
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
          <img
            src={mark as unknown as string}
            width={150}
            height={150}
            alt=""
            style={{ borderRadius: "28px" }}
          />
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
