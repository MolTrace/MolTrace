import type { SVGProps } from "react"

export function SpectraCheckLogoIcon({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="M2.5 14h2.2l1.4-2.6 1.8 5.2 2.3-10.6 2.1 11 1.9-6.1 1.8 3.1h2.1l1.3-2.3 1.5 2.3H21.5" />
    </svg>
  )
}
