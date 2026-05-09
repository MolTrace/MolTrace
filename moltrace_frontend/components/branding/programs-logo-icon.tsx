import type { SVGProps } from "react"

/** Match Lucide sidebar glyph stroke weight at 24×24 viewBox */
const SW = 2

/**
 * Programs mark: three stacked squares + side curves forming an **S** flow (same layout as before).
 * `currentColor` only — matches other sidebar icons.
 */
export function ProgramsLogoIcon({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      shapeRendering="geometricPrecision"
      {...props}
    >
      {/* S upper bowl: left bridge top → middle */}
      <path
        d="M 9.25 6.72 C 5.65 7.35 5.65 8.15 9.25 8.5"
        stroke="currentColor"
        strokeWidth={SW}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* S lower bowl: right bridge middle → bottom */}
      <path
        d="M 14.75 14 C 18.35 14.62 18.35 15.48 14.75 15.78"
        stroke="currentColor"
        strokeWidth={SW}
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Top square */}
      <rect x="9.25" y="1.22" width="5.5" height="5.5" rx="1.15" ry="1.15" fill="currentColor" />
      {/* Middle square */}
      <rect x="9.25" y="8.5" width="5.5" height="5.5" rx="1.15" ry="1.15" fill="currentColor" />
      {/* Bottom square */}
      <rect x="9.25" y="15.78" width="5.5" height="5.5" rx="1.15" ry="1.15" fill="currentColor" />
    </svg>
  )
}
