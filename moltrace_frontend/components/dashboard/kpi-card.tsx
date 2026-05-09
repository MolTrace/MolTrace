"use client"

import Link from "next/link"
import type { CSSProperties, ReactNode } from "react"
import type { LucideIcon } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"

export type KpiCardSeverity = "neutral" | "warning" | "critical" | "success"
export type KpiCardAccent = "teal" | "cyan" | "violet" | "amber"

type KpiCardProps = {
  title: string
  icon: LucideIcon
  value: ReactNode
  sub?: ReactNode
  href?: string
  onClick?: () => void
  onClickLabel?: string
  severity?: KpiCardSeverity
  accent?: KpiCardAccent
}

const ACCENT_VAR: Record<KpiCardAccent, string> = {
  teal: "var(--mt-teal)",
  cyan: "var(--mt-cyan)",
  violet: "var(--mt-violet)",
  amber: "var(--mt-amber)",
}

const SEVERITY_VAR: Record<Exclude<KpiCardSeverity, "neutral">, string> = {
  warning: "var(--mt-amber)",
  critical: "var(--mt-red)",
  success: "var(--mt-green)",
}

const SEVERITY_CARD_CLASS: Record<KpiCardSeverity, string> = {
  neutral: "",
  warning: "border-warning/40",
  critical: "border-destructive/40",
  success: "border-success/40",
}

export function KpiCard({
  title,
  icon: Icon,
  value,
  sub,
  href,
  onClick,
  onClickLabel,
  severity = "neutral",
  accent = "teal",
}: KpiCardProps) {
  const interactive = Boolean(href || onClick)
  const stripeColor =
    severity === "neutral" ? ACCENT_VAR[accent] : SEVERITY_VAR[severity]

  const cardStyle: CSSProperties = {
    borderTop: `3px solid ${stripeColor}`,
  }

  const card = (
    <Card
      className={cn(
        "h-full overflow-hidden rounded-xl py-0 transition-all duration-200",
        SEVERITY_CARD_CLASS[severity],
        interactive && "hover:-translate-y-px hover:border-foreground/20 hover:shadow-md",
      )}
      style={cardStyle}
    >
      <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
        <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          {title}
        </CardTitle>
        <Icon
          className="h-4 w-4 shrink-0"
          style={{ color: stripeColor }}
          aria-hidden
        />
      </CardHeader>
      <CardContent className="pb-5">
        <div
          className="font-mono text-3xl font-bold leading-none tracking-tight tabular-nums"
          style={{ color: stripeColor }}
        >
          {value}
        </div>
        {sub ? <div className="mt-2">{sub}</div> : null}
      </CardContent>
    </Card>
  )

  const wrapperClass =
    "block w-full rounded-xl text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"

  if (href) {
    return (
      <Link href={href} className={wrapperClass} aria-label={`${title} — open detail`}>
        {card}
      </Link>
    )
  }
  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={wrapperClass}
        aria-label={onClickLabel ?? title}
      >
        {card}
      </button>
    )
  }
  return card
}
