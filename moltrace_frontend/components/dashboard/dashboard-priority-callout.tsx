"use client"

import Link from "next/link"
import { ArrowRight } from "lucide-react"
import { AlertCard, type AlertCardVariant } from "@/components/dashboard/alert-card"

export type DashboardPrioritySeverity = "critical" | "warning" | "info"

export type DashboardPriority = {
  severity: DashboardPrioritySeverity
  text: string
  href: string
  cta: string
}

const SEVERITY_ORDER: Record<DashboardPrioritySeverity, number> = {
  critical: 0,
  warning: 1,
  info: 2,
}

const SEVERITY_VARIANT: Record<DashboardPrioritySeverity, AlertCardVariant> = {
  critical: "error",
  warning: "warning",
  info: "info",
}

const SEVERITY_TITLE: Record<DashboardPrioritySeverity, string> = {
  critical: "Critical · Action required",
  warning: "Action required",
  info: "Heads up",
}

type Props = {
  priorities: DashboardPriority[]
}

export function DashboardPriorityCallout({ priorities }: Props) {
  if (priorities.length === 0) {
    return (
      <AlertCard
        variant="success"
        title="All caught up"
        description="No priority items right now."
      />
    )
  }

  const sorted = [...priorities].sort(
    (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
  )
  const top = sorted[0]
  const rest = sorted.slice(1, 3)
  const variant = SEVERITY_VARIANT[top.severity]

  return (
    <AlertCard
      variant={variant}
      title={SEVERITY_TITLE[top.severity]}
      description={top.text}
      action={
        <Link
          href={top.href}
          className="inline-flex items-center gap-1 font-mono text-[11px] font-bold uppercase tracking-[0.12em] text-primary underline-offset-4 hover:underline"
        >
          {top.cta}
          <ArrowRight className="h-3 w-3" aria-hidden />
        </Link>
      }
    >
      {rest.length > 0 ? (
        <ul className="space-y-1 text-xs text-muted-foreground">
          {rest.map((item) => (
            <li key={`${item.severity}-${item.text}`}>
              {item.text} ·{" "}
              <Link href={item.href} className="text-primary underline-offset-4 hover:underline">
                {item.cta}
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </AlertCard>
  )
}
