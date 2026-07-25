import { ImageResponse } from "next/og"

import { SITE_NAME, SITE_TAGLINE } from "@/lib/seo/site"

// Default social-share card (1200×630) inherited by every route that doesn't
// define its own opengraph-image. Rendered at the edge with next/og — no static
// asset to ship, no font files to fetch (system sans keeps it fast + reliable).
export const runtime = "edge"
export const alt = `${SITE_NAME} — ${SITE_TAGLINE}`
export const size = { width: 1200, height: 630 }
export const contentType = "image/png"

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          height: "100%",
          width: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background:
            "radial-gradient(120% 120% at 15% 0%, #0d1a2b 0%, #070b12 55%, #05070c 100%)",
          padding: "80px",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "24px" }}>
          <div
            style={{
              width: "72px",
              height: "72px",
              borderRadius: "18px",
              background: "linear-gradient(135deg, #2dd4bf 0%, #22d3ee 100%)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "40px",
              fontWeight: 800,
              color: "#04121a",
            }}
          >
            M
          </div>
          <div style={{ fontSize: "40px", fontWeight: 700, color: "#e6f0f7" }}>
            {SITE_NAME}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          <div
            style={{
              fontSize: "68px",
              lineHeight: 1.05,
              fontWeight: 800,
              color: "#f4f9fc",
              maxWidth: "960px",
              letterSpacing: "-0.02em",
            }}
          >
            The audit-ready evidence engine for pharmaceutical R&amp;D
          </div>
          <div style={{ fontSize: "30px", color: "#7dd3e8", fontWeight: 500 }}>
            Spectroscopy · Reaction optimization · Regulatory intelligence
          </div>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "16px",
            fontSize: "26px",
            color: "#9fb3c2",
          }}
        >
          <div
            style={{
              width: "14px",
              height: "14px",
              borderRadius: "50%",
              background: "#a78bfa",
            }}
          />
          moltrace.co
        </div>
      </div>
    ),
    { ...size },
  )
}
