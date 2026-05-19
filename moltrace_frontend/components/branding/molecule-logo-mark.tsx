"use client"

import { useId } from "react"
import { cn } from "@/lib/utils"

type MoleculeLogoMarkProps = {
  className?: string
  textClassName?: string
}

const SQRT3 = Math.sqrt(3)

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

function honeycombCenters(R: number, pad: number): Array<[number, number]> {
  const dx = SQRT3 * R
  const dy = 1.5 * R
  const centers: Array<[number, number]> = []
  for (let row = -2; ; row++) {
    const cy = pad + row * dy
    if (cy > 64 + R) break
    const ox = (row % 2) * (dx / 2)
    for (let col = -2; ; col++) {
      const cx = pad + ox + col * dx
      if (cx > 64 + R) break
      centers.push([cx, cy])
    }
  }
  return centers
}

/** Dark blue tile behind the mark (explicit hex so PWA raster matches). */
const LOGO_BACKGROUND_DARK_BLUE = "#051f3a"
/** Honeycomb stroke color — Bright honeycomb stroke color. */
const HONEYCOMB_BRIGHT_BLUE = "#26C6FF"
/** Ring along the hex edge — matches the "Trace" cyan in the wordmark; visible on light and dark page backgrounds. */
const RING_TRACE_CYAN = HONEYCOMB_BRIGHT_BLUE
/** Flat-top hex, fitting a 64×64 viewBox — width 64, height 64 with side points at (0,32) and (64,32). */
const HEX_OUTER_POINTS = "16,0 48,0 64,32 48,64 16,64 0,32"
/** Same hex in objectBoundingBox (0–1) coords for the clipPath. */
const HEX_BB_VERTICES: [number, number][] = [
  [0.25, 0],
  [0.75, 0],
  [1, 0.5],
  [0.75, 1],
  [0.25, 1],
  [0, 0.5],
]

function sub2(a: [number, number], b: [number, number]): [number, number] {
  return [a[0] - b[0], a[1] - b[1]]
}

function add2(a: [number, number], b: [number, number]): [number, number] {
  return [a[0] + b[0], a[1] + b[1]]
}

function scale2(v: [number, number], s: number): [number, number] {
  return [v[0] * s, v[1] * s]
}

function norm2(v: [number, number]): [number, number] {
  const l = Math.hypot(v[0], v[1])
  return l < 1e-9 ? [0, 0] : [v[0] / l, v[1] / l]
}

/**
 * Convex polygon in objectBoundingBox (0–1) space, with small circular arc
 * corners for smoother clip edges in light / dark / HiDPI. Generic over the
 * vertex list so the same routine renders hex, heptagon, etc.
 */
function roundedPolyPathD(v: [number, number][], cornerR: number): string {
  const n = v.length
  const pStart: [number, number][] = []
  const pEnd: [number, number][] = []
  for (let i = 0; i < n; i++) {
    const prev = v[(i + n - 1) % n]
    const curr = v[i]
    const next = v[(i + 1) % n]
    const uIn = norm2(sub2(prev, curr))
    const uOut = norm2(sub2(next, curr))
    const dot = Math.max(-1, Math.min(1, uIn[0] * uOut[0] + uIn[1] * uOut[1]))
    const angle = Math.acos(dot)
    const cut = cornerR / Math.tan(angle / 2)
    pStart.push(add2(curr, scale2(uIn, cut)))
    pEnd.push(add2(curr, scale2(uOut, cut)))
  }

  let d = `M ${fmt(pStart[0])}`
  for (let i = 0; i < n; i++) {
    d += arcTo(pStart[i], pEnd[i], cornerR)
    d += ` L ${fmt(pStart[(i + 1) % n])}`
  }
  d += " Z"
  return d
}

function fmtN(n: number) {
  return n.toFixed(5)
}

function fmt(p: [number, number]) {
  return `${p[0].toFixed(5)} ${p[1].toFixed(5)}`
}

/** SVG elliptical arc from current point to p1 with radius r (objectBoundingBox space). */
function arcTo(p0: [number, number], p1: [number, number], r: number): string {
  const dx = p1[0] - p0[0]
  const dy = p1[1] - p0[1]
  const chord = Math.hypot(dx, dy)
  if (chord < 1e-8) return ""
  if (chord > 2 * r - 1e-6) {
    return ` L ${fmt(p1)}`
  }
  const midX = (p0[0] + p1[0]) / 2
  const midY = (p0[1] + p1[1]) / 2
  const h = Math.sqrt(r * r - (chord / 2) * (chord / 2))
  const ux = -dy / chord
  const uy = dx / chord
  const cx1 = midX + ux * h
  const cy1 = midY + uy * h
  const cx2 = midX - ux * h
  const cy2 = midY - uy * h
  const towardCenter = (cx: number, cy: number) => Math.hypot(cx - 0.5, cy - 0.5)
  const use1 = towardCenter(cx1, cy1) <= towardCenter(cx2, cy2)
  const cx = use1 ? cx1 : cx2
  const cy = use1 ? cy1 : cy2
  const a0 = Math.atan2(p0[1] - cy, p0[0] - cx)
  const a1 = Math.atan2(p1[1] - cy, p1[0] - cx)
  let delta = a1 - a0
  while (delta > Math.PI) delta -= 2 * Math.PI
  while (delta < -Math.PI) delta += 2 * Math.PI
  const sweep: 0 | 1 = delta > 0 ? 1 : 0
  const largeArc: 0 | 1 = Math.abs(delta) > Math.PI / 2 ? 1 : 0
  return ` A ${fmtN(r)} ${fmtN(r)} 0 ${largeArc} ${sweep} ${fmt(p1)}`
}

/** ~3% of box — strong enough to soften jaggies, small enough to match honeycomb */
const HEX_CORNER_R = 0.028

export function MoleculeLogoMark({ className, textClassName }: MoleculeLogoMarkProps) {
  const rid = useId().replace(/:/g, "")
  const clipId = `moltrace-logo-hex-${rid}`
  const maskId = `moltrace-logo-cutout-${rid}`
  const glowId = `moltrace-logo-glow-${rid}`
  const liftId = `moltrace-logo-lift-${rid}`
  const engraveId = `moltrace-logo-engrave-${rid}`
  const mGradId = `moltrace-logo-mgrad-${rid}`
  const topFaceId = `moltrace-logo-topface-${rid}`
  const rightFaceId = `moltrace-logo-rightface-${rid}`
  const leftFaceId = `moltrace-logo-leftface-${rid}`
  const R = 5.35
  const centers = honeycombCenters(R, 5)
  const letterClassName = cn("select-none", textClassName)
  const clipPathD = roundedPolyPathD(HEX_BB_VERTICES, HEX_CORNER_R)

  return (
    <div
      className={cn(
        "relative flex items-center justify-center overflow-hidden",
        /* Promote own layer + gentler edge composite in light and dark */
        "[transform:translateZ(0)] [-webkit-backface-visibility:hidden] [backface-visibility:hidden]",
        className,
      )}
      style={{
        backgroundColor: LOGO_BACKGROUND_DARK_BLUE,
        clipPath: `url(#${clipId})`,
        WebkitClipPath: `url(#${clipId})`,
      }}
      aria-hidden="true"
    >
      <svg
        width={0}
        height={0}
        className="pointer-events-none absolute overflow-hidden"
        aria-hidden
      >
        <defs>
          <clipPath id={clipId} clipPathUnits="objectBoundingBox">
            <path d={clipPathD} clipRule="nonzero" />
          </clipPath>
        </defs>
      </svg>
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 64 64"
        fill="none"
        shapeRendering="geometricPrecision"
        aria-hidden="true"
      >
        <defs>
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
          {/* Drop shadow filter — raises the m off the surface (unused now,
              kept for parity with prior versions). */}
          <filter id={liftId} x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur in="SourceAlpha" stdDeviation="0.6" result="blur" />
            <feOffset in="blur" dx="0" dy="0.9" result="offset" />
            <feComponentTransfer in="offset" result="shadow">
              <feFuncA type="linear" slope="0.7" />
            </feComponentTransfer>
            <feMerge>
              <feMergeNode in="shadow" />
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
          {/* Subtle vertical white gradient — bright top → soft cool bottom.
              The engrave filter adds the recess shading on top of this. */}
          <linearGradient id={mGradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#FFFFFF" />
            <stop offset="55%" stopColor="#F2FAFF" />
            <stop offset="100%" stopColor="#CFE9FF" />
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
            embedded on the surface. */}
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
        {/* m engraved into the cube — dark cavity gradient + inner shadow
            on top rim + inner highlight on lit floor → reads as inserted
            into the cube surface with visible 3D depth. */}
        <g
          className={letterClassName}
          fontFamily="ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
          fontSize={40}
          fontWeight={900}
          textAnchor="middle"
          filter={`url(#${engraveId})`}
        >
          <text x="32" y="32" dy="0.33em" fill={`url(#${mGradId})`}>
            m
          </text>
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
