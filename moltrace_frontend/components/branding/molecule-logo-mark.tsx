"use client"

import { useId } from "react"
import { cn } from "@/lib/utils"

type MoleculeLogoMarkProps = {
  className?: string
  textClassName?: string
}

/** Flat-top hexagon circumradius R — vertex angles π/6 + kπ/3 */
function flatTopHexPoints(cx: number, cy: number, R: number): string {
  const pts: string[] = []
  for (let i = 0; i < 6; i++) {
    const ang = Math.PI / 6 + (i * Math.PI) / 3
    const x = cx + R * Math.cos(ang)
    const y = cy + R * Math.sin(ang)
    pts.push(`${x.toFixed(3)},${y.toFixed(3)}`)
  }
  return pts.join(" ")
}

/** Dark blue tile behind the mark (explicit hex so PWA raster matches). */
const LOGO_BACKGROUND_DARK_BLUE = "#051f3a"
/** Honeycomb stroke color — Bright honeycomb stroke color. */
const HONEYCOMB_BRIGHT_BLUE = "#26C6FF"
/** Ring along the hex edge — matches the "Trace" cyan in the wordmark; visible on light and dark page backgrounds. */
const RING_TRACE_CYAN = HONEYCOMB_BRIGHT_BLUE
/** Engraved m fill — white carving floor inside the cube. */
const M_ENGRAVED_WHITE = "#FFFFFF"
/** Engraved m bevels — use cube-face colors so the carving edges belong to the cube material. */
const M_ENGRAVE_EDGE_LIGHT = "#2E78AC"
const M_ENGRAVE_EDGE_DARK = "#062337"
/** Flat-top hex, fitting a 64×64 viewBox — width 64, height 64 with side points at (0,32) and (64,32). */
const HEX_OUTER_POINTS = "16,0 48,0 64,32 48,64 16,64 0,32"
export function MoleculeLogoMark({ className, textClassName }: MoleculeLogoMarkProps) {
  const rid = useId().replace(/:/g, "")
  const clipId = `moltrace-logo-hex-${rid}`
  const maskId = `moltrace-logo-cutout-${rid}`
  const glowId = `moltrace-logo-glow-${rid}`
  const engraveId = `moltrace-logo-engrave-${rid}`
  const mRecessGradId = `moltrace-logo-mrecess-${rid}`
  const topFaceId = `moltrace-logo-topface-${rid}`
  const rightFaceId = `moltrace-logo-rightface-${rid}`
  const leftFaceId = `moltrace-logo-leftface-${rid}`
  const letterClassName = cn("select-none", textClassName)

  return (
    <div
      className={cn(
        "relative flex items-center justify-center",
        /* Promote own layer for consistent SVG antialiasing on mobile GPUs. */
        "[transform:translateZ(0)] [-webkit-backface-visibility:hidden] [backface-visibility:hidden]",
        className,
      )}
      aria-hidden="true"
    >
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 64 64"
        fill="none"
        shapeRendering="geometricPrecision"
        aria-hidden="true"
      >
        <defs>
          <clipPath id={clipId} clipPathUnits="userSpaceOnUse">
            <polygon points={HEX_OUTER_POINTS} />
          </clipPath>
          {/* Cutout mask — the m glyph subtracts from the lattice. */}
          <mask id={maskId} maskUnits="userSpaceOnUse" x="0" y="0" width="64" height="64">
            <rect width="64" height="64" fill="#fff" />
            <g
              className={letterClassName}
              fontFamily="ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
              fontSize={40}
              fontWeight={900}
              textAnchor="middle"
            >
              <text x="32" y="32" dy="0.33em" fill="#000">
                m
              </text>
            </g>
          </mask>
          {/* Cyan neon glow filter — alien bioluminescence around lattice. */}
          <filter id={glowId} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="1.1" result="blur" />
            <feFlood floodColor={HONEYCOMB_BRIGHT_BLUE} floodOpacity="0.85" result="flood" />
            <feComposite in="flood" in2="blur" operator="in" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          {/* Engrave filter — inner shadow on top edge + inner highlight on
              bottom edge so the m reads as carved into the cube surface
              with visible 3D depth. */}
          <filter id={engraveId} x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur in="SourceAlpha" stdDeviation="0.8" result="blur" />
            {/* Top inner shadow: subtract a downward-offset blob from the
                source alpha — leaves a darkened band at the TOP rim. */}
            <feOffset in="blur" dy="1.4" result="offsetDown" />
            <feComposite
              in="SourceAlpha"
              in2="offsetDown"
              operator="out"
              result="topRing"
            />
            <feFlood floodColor="#000" floodOpacity="0.9" result="darkColor" />
            <feComposite in="darkColor" in2="topRing" operator="in" result="topShadow" />
            {/* Bottom inner highlight: subtract an upward-offset blob,
                color it with brand cyan-tinted light for a lit-floor look. */}
            <feOffset in="blur" dy="-1.4" result="offsetUp" />
            <feComposite
              in="SourceAlpha"
              in2="offsetUp"
              operator="out"
              result="bottomRing"
            />
            <feFlood floodColor="#9DD7F2" floodOpacity="0.6" result="lightColor" />
            <feComposite
              in="lightColor"
              in2="bottomRing"
              operator="in"
              result="bottomHighlight"
            />
            <feMerge>
              <feMergeNode in="SourceGraphic" />
              <feMergeNode in="bottomHighlight" />
              <feMergeNode in="topShadow" />
            </feMerge>
          </filter>
          {/* White floor of the engraved m — the cube is masked away in
              the letter shape, and this fills that void as a recessed cavity. */}
          <linearGradient id={mRecessGradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={M_ENGRAVED_WHITE} />
            <stop offset="100%" stopColor={M_ENGRAVED_WHITE} />
          </linearGradient>
          {/* Isometric cube face gradients — top brightest (sky-lit),
              right medium, left darkest (shadow side). */}
          <linearGradient id={topFaceId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2E78AC" />
            <stop offset="100%" stopColor="#0F3A5C" />
          </linearGradient>
          <linearGradient id={rightFaceId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#194C70" />
            <stop offset="100%" stopColor="#062337" />
          </linearGradient>
          <linearGradient id={leftFaceId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0D3050" />
            <stop offset="100%" stopColor="#021326" />
          </linearGradient>
        </defs>
        <g clipPath={`url(#${clipId})`}>
          <rect width={64} height={64} fill={LOGO_BACKGROUND_DARK_BLUE} />
          {/* Isometric cube — three shaded faces meeting at the front corner
              (hex center). Masked so the m silhouette cuts cleanly out of
              the cube body. */}
          <g mask={`url(#${maskId})`}>
            <polygon points="16,0 48,0 32,32 0,32" fill={`url(#${topFaceId})`} />
            <polygon points="48,0 64,32 48,64 32,32" fill={`url(#${rightFaceId})`} />
            <polygon points="32,32 48,64 16,64 0,32" fill={`url(#${leftFaceId})`} />
          </g>
          {/* One honeycomb cell at the geometric centroid of each face,
              skewed to follow the face's perspective so it reads as
              embedded on the surface with the restored cyan glow. */}
          <g
            mask={`url(#${maskId})`}
            filter={`url(#${glowId})`}
            strokeWidth={1.2}
            strokeLinejoin="miter"
            strokeLinecap="butt"
            fill="none"
          >
            {/* TOP face — shifted up along the face. */}
            <g transform="translate(24 14) matrix(1 0 -0.5 1 0 0) translate(-24 -14)">
              <polygon
                points={flatTopHexPoints(24, 14, 4)}
                stroke={HONEYCOMB_BRIGHT_BLUE}
              />
            </g>
            {/* RIGHT face — fine-tuned up and left. */}
            <g transform="translate(52 23) matrix(0.5 1 -0.5 1 0 0) translate(-52 -23)">
              <polygon
                points={flatTopHexPoints(52, 23, 4)}
                stroke={HONEYCOMB_BRIGHT_BLUE}
              />
            </g>
            {/* LEFT face — shifted right along the face for visual balance. */}
            <g transform="translate(27 53) matrix(1 0 0.5 1 0 0) translate(-27 -53)">
              <polygon
                points={flatTopHexPoints(27, 53, 4)}
                stroke={HONEYCOMB_BRIGHT_BLUE}
              />
            </g>
          </g>
          {/* Cube wireframe — three glowing cyan edges form the Y-junction
              at the front corner, defining the cube structure. */}
          <g
            mask={`url(#${maskId})`}
            filter={`url(#${glowId})`}
            stroke={HONEYCOMB_BRIGHT_BLUE}
            strokeWidth={1.4}
            strokeLinecap="round"
            fill="none"
          >
            <line x1="32" y1="32" x2="48" y2="0" />
            <line x1="32" y1="32" x2="48" y2="64" />
            <line x1="32" y1="32" x2="0" y2="32" />
          </g>
          {/* Engraved m — the cube faces are cut away by maskId above. The dark
              letter floor and offset bevel strokes sit inside that cutout, so
              the glyph reads as carved into the cube rather than raised above it. */}
          <g
            className={letterClassName}
            fontFamily="ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
            fontSize={40}
            fontWeight={900}
            textAnchor="middle"
          >
            <text
              x="32"
              y="32"
              dy="0.33em"
              fill={`url(#${mRecessGradId})`}
              filter={`url(#${engraveId})`}
            >
              m
            </text>
            <text
              x="31.6"
              y="31.1"
              dy="0.33em"
              fill="none"
              stroke={M_ENGRAVE_EDGE_LIGHT}
              strokeWidth={1.05}
              opacity={0.58}
            >
              m
            </text>
            <text
              x="32.7"
              y="33.1"
              dy="0.33em"
              fill="none"
              stroke={M_ENGRAVE_EDGE_DARK}
              strokeWidth={2.1}
              opacity={0.72}
            >
              m
            </text>
          </g>
        </g>
        {/* Trace-cyan ring along the hex outer edge. */}
        <polygon
          points={HEX_OUTER_POINTS}
          fill="none"
          stroke={RING_TRACE_CYAN}
          strokeWidth={4}
          strokeLinejoin="miter"
        />
      </svg>
    </div>
  )
}
