"use client"

import { cn } from "@/lib/utils"

export type ConfidenceRingAccent = "teal" | "cyan" | "violet" | "amber"

const ACCENT_VAR: Record<ConfidenceRingAccent, string> = {
  teal: "var(--mt-teal)",
  cyan: "var(--mt-cyan)",
  violet: "var(--mt-violet)",
  amber: "var(--mt-amber)",
}

type ConfidenceRingProps = {
  value: number
  size?: number
  accent?: ConfidenceRingAccent
  ariaLabel?: string
  className?: string
}

export function ConfidenceRing({
  value,
  size = 64,
  accent = "teal",
  ariaLabel,
  className,
}: ConfidenceRingProps) {
  const safeValue = Math.max(0, Math.min(100, value))
  const r = size * 0.38
  const circ = 2 * Math.PI * r
  const dash = (safeValue / 100) * circ
  const color = ACCENT_VAR[accent]

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={ariaLabel ?? `Confidence ${Math.round(safeValue)} percent`}
      className={cn("shrink-0", className)}
    >
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="currentColor"
        strokeWidth={size * 0.06}
        className="text-muted opacity-40"
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth={size * 0.06}
        strokeDasharray={`${dash} ${circ}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ filter: `drop-shadow(0 0 6px ${color}55)` }}
      />
      <text
        x={size / 2}
        y={size / 2 + size * 0.04}
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize={size * 0.22}
        fontWeight={700}
        fill={color}
        className="font-mono tabular-nums"
      >
        {Math.round(safeValue)}%
      </text>
    </svg>
  )
}
