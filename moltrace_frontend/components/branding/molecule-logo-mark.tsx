"use client"

import { useId } from "react"
import { cn } from "@/lib/utils"

type MoleculeLogoMarkProps = {
  className?: string
  textClassName?: string
}

/**
 * The MolTrace mark: an extruded hexagonal prism of neon cyan, three honeycomb
 * cells and three trace lines inside it, and a raised `m` catching the rim light.
 *
 * Geometry and palette are exported-by-duplication into
 * `scripts/generate-pwa-icons.mjs`, which rasterizes this same drawing into the
 * favicon, PWA and social assets. **Change one and you must change the other** —
 * a mark that disagrees with its own favicon is the drift this file's constants
 * exist to prevent.
 */

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

/**
 * The mark's outer hexagon, inset from the 64×64 viewBox so the neon bloom has
 * somewhere to fall. At inset 0 this is the historical edge-to-edge silhouette;
 * the glow was clipped flat against the viewport there, which is what made the
 * old mark read as a sticker rather than a lit object.
 */
function markHexPoints(inset: number): string {
  const r = 32 - inset
  const h = r / 2
  return [
    `${32 - h},${32 - r}`,
    `${32 + h},${32 - r}`,
    `${32 + r},32`,
    `${32 + h},${32 + r}`,
    `${32 - h},${32 + r}`,
    `${32 - r},32`,
  ].join(" ")
}

/** Dark blue tile behind the mark (explicit hex so PWA raster matches). */
const LOGO_BACKGROUND_DARK_BLUE = "#051f3a"
/** Honeycomb + trace-line stroke — the "Trace" cyan from the wordmark. */
const HONEYCOMB_BRIGHT_BLUE = "#26C6FF"
/** The neon tube's hot core, where the cyan blows out toward white. */
const NEON_CORE_WHITE = "#CDF0FF"
/** The prism's far edge, catching light at a glancing angle. */
const PRISM_SHELL_BLUE = "#7FD8FF"
/** Rim light along the raised m — the same cyan, softened. */
const M_RIM_LIGHT = "#8FDCFF"
/** The m's lit face, cooling from white at the top to a pale steel below. */
const M_FACE_TOP = "#FFFFFF"
const M_FACE_BOTTOM = "#B9D8EC"
/** The shadow the raised m casts onto the prism floor. */
const M_CAST_SHADOW = "#020C17"

/** Room left around the hexagon for the bloom, in viewBox units. */
const HEX_GLOW_INSET = 3.5
const HEX_OUTER_POINTS = markHexPoints(HEX_GLOW_INSET)

export function MoleculeLogoMark({ className, textClassName }: MoleculeLogoMarkProps) {
  const rid = useId().replace(/:/g, "")
  const clipId = `moltrace-logo-hex-${rid}`
  const maskId = `moltrace-logo-cutout-${rid}`
  const glowId = `moltrace-logo-glow-${rid}`
  const bloomId = `moltrace-logo-bloom-${rid}`
  const castId = `moltrace-logo-cast-${rid}`
  const mFaceId = `moltrace-logo-mface-${rid}`
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
          {/* Cutout mask — the m subtracts from the lattice, so no trace line
              and no honeycomb cell ever crosses the glyph. This is what keeps
              the letter readable at 20px, where a crossing line reads as noise. */}
          <mask id={maskId} maskUnits="userSpaceOnUse" x="0" y="0" width="64" height="64">
            <rect width="64" height="64" fill="#fff" />
            <g
              className={letterClassName}
              fontFamily="ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
              fontSize={34}
              fontWeight={900}
              textAnchor="middle"
            >
              <text x="32" y="32" dy="0.33em" fill="#000" stroke="#000" strokeWidth={1.5}>
                m
              </text>
            </g>
          </mask>
          {/* Tight glow — the lattice inside the prism. */}
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
          {/* Wide bloom — the light the prism edge throws past its own silhouette.
              Drawn outside the clip, which is the whole reason for the inset. */}
          <filter id={bloomId} x="-75%" y="-75%" width="250%" height="250%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="2.6" result="wide" />
            <feFlood floodColor={HONEYCOMB_BRIGHT_BLUE} floodOpacity="0.9" result="flood" />
            <feComposite in="flood" in2="wide" operator="in" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="coloredBlur" />
            </feMerge>
          </filter>
          {/* The m's cast shadow — offset down-right, so the light reads as
              coming from the upper-left, same as the prism's lit edges. */}
          <filter id={castId} x="-40%" y="-40%" width="180%" height="180%">
            <feDropShadow
              dx="0.9"
              dy="1.3"
              stdDeviation="0.9"
              floodColor={M_CAST_SHADOW}
              floodOpacity="0.85"
            />
          </filter>
          {/* The m's face — white where the key light lands, cooling to steel. */}
          <linearGradient id={mFaceId} x1="0" y1="0" x2="0.25" y2="1">
            <stop offset="0%" stopColor={M_FACE_TOP} />
            <stop offset="55%" stopColor={M_FACE_TOP} />
            <stop offset="100%" stopColor={M_FACE_BOTTOM} />
          </linearGradient>
          {/* Interior planes. Far darker than the neon so the lattice and the
              letter stay the two things the eye resolves first at small sizes. */}
          <linearGradient id={topFaceId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#14425F" />
            <stop offset="100%" stopColor="#0A2A45" />
          </linearGradient>
          <linearGradient id={rightFaceId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0F3552" />
            <stop offset="100%" stopColor="#061C2E" />
          </linearGradient>
          <linearGradient id={leftFaceId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0A2438" />
            <stop offset="100%" stopColor="#03101E" />
          </linearGradient>
        </defs>

        {/* 1. The bloom, unclipped — light spilling past the prism's edge. */}
        <polygon
          points={HEX_OUTER_POINTS}
          fill="none"
          stroke={HONEYCOMB_BRIGHT_BLUE}
          strokeWidth={2.4}
          strokeLinejoin="miter"
          filter={`url(#${bloomId})`}
          opacity={0.75}
        />

        {/* 2. Everything inside the prism. */}
        <g clipPath={`url(#${clipId})`}>
          <rect width={64} height={64} fill={LOGO_BACKGROUND_DARK_BLUE} />
          <g mask={`url(#${maskId})`}>
            <polygon points="16,0 48,0 32,32 0,32" fill={`url(#${topFaceId})`} />
            <polygon points="48,0 64,32 48,64 32,32" fill={`url(#${rightFaceId})`} />
            <polygon points="32,32 48,64 16,64 0,32" fill={`url(#${leftFaceId})`} />
          </g>
          {/* One honeycomb cell per face, skewed to lie flat on that face. */}
          <g
            mask={`url(#${maskId})`}
            filter={`url(#${glowId})`}
            strokeWidth={1.1}
            strokeLinejoin="miter"
            strokeLinecap="butt"
            fill="none"
          >
            <g transform="translate(24 14) matrix(1 0 -0.5 1 0 0) translate(-24 -14)">
              <polygon points={flatTopHexPoints(24, 14, 4)} stroke={HONEYCOMB_BRIGHT_BLUE} />
            </g>
            <g transform="translate(52 23) matrix(0.5 1 -0.5 1 0 0) translate(-52 -23)">
              <polygon points={flatTopHexPoints(52, 23, 4)} stroke={HONEYCOMB_BRIGHT_BLUE} />
            </g>
            <g transform="translate(27 53) matrix(1 0 0.5 1 0 0) translate(-27 -53)">
              <polygon points={flatTopHexPoints(27, 53, 4)} stroke={HONEYCOMB_BRIGHT_BLUE} />
            </g>
          </g>
          {/* Three trace lines meeting at the front corner. */}
          <g
            mask={`url(#${maskId})`}
            filter={`url(#${glowId})`}
            stroke={HONEYCOMB_BRIGHT_BLUE}
            strokeWidth={1.3}
            strokeLinecap="round"
            fill="none"
          >
            <line x1="32" y1="32" x2="48" y2="0" />
            <line x1="32" y1="32" x2="48" y2="64" />
            <line x1="32" y1="32" x2="0" y2="32" />
          </g>
        </g>

        {/* 3. The prism edge: far shell, neon tube, hot core. Drawn outside the
               clip so the stroke sits centred on the silhouette rather than
               being halved by it. */}
        <polygon
          points={markHexPoints(HEX_GLOW_INSET - 1.15)}
          fill="none"
          stroke={PRISM_SHELL_BLUE}
          strokeWidth={0.7}
          strokeLinejoin="miter"
          opacity={0.4}
        />
        <polygon
          points={HEX_OUTER_POINTS}
          fill="none"
          stroke={HONEYCOMB_BRIGHT_BLUE}
          strokeWidth={2.3}
          strokeLinejoin="miter"
        />
        <polygon
          points={HEX_OUTER_POINTS}
          fill="none"
          stroke={NEON_CORE_WHITE}
          strokeWidth={0.85}
          strokeLinejoin="miter"
          opacity={0.9}
        />

        {/* 4. The raised m — cast shadow, lit face, then the cyan rim the prism
               throws onto its edges. */}
        <g
          className={letterClassName}
          fontFamily="ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
          fontSize={34}
          fontWeight={900}
          textAnchor="middle"
        >
          <text
            x="32"
            y="32"
            dy="0.33em"
            fill={`url(#${mFaceId})`}
            filter={`url(#${castId})`}
          >
            m
          </text>
          <text
            x="32"
            y="32"
            dy="0.33em"
            fill="none"
            stroke={M_RIM_LIGHT}
            strokeWidth={0.9}
            strokeLinejoin="round"
            opacity={0.95}
          >
            m
          </text>
        </g>
      </svg>
    </div>
  )
}
