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
 * Flat-top hex in objectBoundingBox (0–1), same framing as legacy CSS polygon(25% 0, 75% 0, …),
 * with circular arc corners for smoother clip edges in light / dark / HiDPI.
 */
function roundedFlatTopHexPathD(cornerR: number): string {
  const v: [number, number][] = [
    [0.25, 0],
    [0.75, 0],
    [1, 0.5],
    [0.75, 1],
    [0.25, 1],
    [0, 0.5],
  ]
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
  const R = 5.35
  const centers = honeycombCenters(R, 5)
  const letterClassName = cn("select-none", textClassName)
  const clipPathD = roundedFlatTopHexPathD(HEX_CORNER_R)

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
        {/* Honeycomb — crisp strokes, no opacity/filter */}
        <g strokeWidth={2} strokeLinejoin="miter" strokeLinecap="butt" fill="none">
          {centers.map(([cx, cy], i) => (
            <polygon
              key={`front-${i}`}
              points={flatTopHexPoints(cx, cy, R)}
              stroke={HONEYCOMB_BRIGHT_BLUE}
            />
          ))}
        </g>
        <g
          className={letterClassName}
          fontFamily="ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
          fontSize={44}
          fontWeight={900}
          textAnchor="middle"
        >
          <text
            x="32"
            y="31.5"
            dy="0.33em"
            fill="none"
            stroke={LOGO_BACKGROUND_DARK_BLUE}
            strokeWidth={7}
            strokeLinecap="round"
            strokeLinejoin="round"
            paintOrder="stroke"
          >
            m
          </text>
          <text x="32" y="31.5" dy="0.33em" fill="#FFFFFF">
            m
          </text>
        </g>
      </svg>
    </div>
  )
}
