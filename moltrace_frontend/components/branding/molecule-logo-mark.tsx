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
  for (let row = 0; ; row++) {
    const cy = pad + row * dy
    if (cy > 64 - pad - R * 0.35) break
    const ox = (row % 2) * (dx / 2)
    for (let col = 0; ; col++) {
      const cx = pad + ox + col * dx
      if (cx > 64 - pad - R * 0.35) break
      centers.push([cx, cy])
    }
  }
  return centers
}

function cornerHighlightIndices(centers: Array<[number, number]>): Set<number> {
  const indexed = centers.map(([x, y], index) => ({ index, x, y }))
  const topLeft = [...indexed].sort((a, b) => (a.x + a.y) - (b.x + b.y))[0]?.index
  const topRight = [...indexed].sort((a, b) => (b.x - b.y) - (a.x - a.y))[0]?.index
  const bottomLeft = [...indexed].sort((a, b) => (b.y - b.x) - (a.y - a.x))[0]?.index
  const bottomRight = [...indexed].sort((a, b) => (b.x + b.y) - (a.x + a.y))[0]?.index
  return new Set([topLeft, topRight, bottomLeft, bottomRight].filter((v): v is number => v != null))
}

export function MoleculeLogoMark({ className, textClassName }: MoleculeLogoMarkProps) {
  const R = 5.35
  const centers = honeycombCenters(R, 5)
  const highlighted = cornerHighlightIndices(centers)
  const traceBlue = "#42A5F5"
  const honeycombWhite = "#FFFFFF"
  const markBlue = "#FFFFFF"
  const letterClassName = [
    "relative z-20 flex h-full w-full items-center justify-center font-black leading-none tracking-tight text-base text-white",
    textClassName,
  ]
    .filter(Boolean)
    .join(" ")

  return (
    <div
      className={cn(
        "relative flex items-center justify-center overflow-hidden rounded-md bg-black",
        className
      )}
      aria-hidden="true"
    >
      <svg
        className="absolute inset-0 h-full w-full text-zinc-300 dark:text-zinc-200"
        viewBox="0 0 64 64"
        fill="none"
        aria-hidden="true"
      >
        {/* Honeycomb */}
        <g strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" fill="none">
          {centers.map(([cx, cy], i) => (
            <polygon
              key={`front-${i}`}
              points={flatTopHexPoints(cx, cy, R)}
              stroke={highlighted.has(i) ? traceBlue : honeycombWhite}
            />
          ))}
        </g>
      </svg>
      <span
        className={letterClassName}
        style={{
          textShadow: "0 0 2px rgb(0 0 0), 0 1px 3px rgb(0 0 0 / 0.95)",
          WebkitTextStroke: "0.6px currentColor",
          color: markBlue,
        }}
      >
        <span className="block -translate-y-px text-center">m</span>
      </span>
    </div>
  )
}
