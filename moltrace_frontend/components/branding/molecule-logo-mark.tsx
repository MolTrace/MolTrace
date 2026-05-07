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

/** Dark blue tile behind the mark (explicit hex so PWA raster matches). */
const LOGO_BACKGROUND_DARK_BLUE = "#051f3a"
/** Honeycomb stroke color — Bright honeycomb stroke color. */
const HONEYCOMB_BRIGHT_BLUE = "#26C6FF"

/** Flat-top regular hexagon inscribed in the logo box (aligned with honeycomb cells). */
const LOGO_HEX_CLIP =
  "polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%)"

export function MoleculeLogoMark({ className, textClassName }: MoleculeLogoMarkProps) {
  const R = 5.35
  const centers = honeycombCenters(R, 5)
  const letterClassName = cn("select-none", textClassName)

  return (
    <div
      className={cn("relative flex items-center justify-center overflow-hidden", className)}
      style={{
        backgroundColor: LOGO_BACKGROUND_DARK_BLUE,
        clipPath: LOGO_HEX_CLIP,
        WebkitClipPath: LOGO_HEX_CLIP,
      }}
      aria-hidden="true"
    >
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 64 64"
        fill="none"
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
          fontSize={36}
          fontWeight={900}
          textAnchor="middle"
        >
          <text
            x="32"
            y="32"
            dy="0.35em"
            fill="none"
            stroke={LOGO_BACKGROUND_DARK_BLUE}
            strokeWidth={7.5}
            strokeLinecap="round"
            strokeLinejoin="round"
            paintOrder="stroke"
          >
            m
          </text>
          <text
            x="32"
            y="32"
            dy="0.35em"
            fill="#FFFFFF"
          >
            m
          </text>
        </g>
      </svg>
    </div>
  )
}
