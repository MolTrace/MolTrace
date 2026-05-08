"use client"

import Link from "next/link"
import { AlertTriangle, ArrowRight, CheckCircle2, AlertCircle } from "lucide-react"
import { cn } from "@/lib/utils"

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

const SEVERITY_STYLES: Record<DashboardPrioritySeverity, { container: string; icon: string }> = {
  critical: {
    container: "border-destructive/40 bg-destructive/5",
    icon: "text-destructive",
  },
  warning: {
    container: "border-warning/40 bg-warning/5",
    icon: "text-warning",
  },
  info: {
    container: "border-border bg-muted/30",
    icon: "text-muted-foreground",
  },
}

type Props = {
  priorities: DashboardPriority[]
}

export function DashboardPriorityCallout({ priorities }: Props) {
  if (priorities.length === 0) {
    return (
      <div
        role="status"
        className="flex items-center gap-3 rounded-lg border border-success/40 bg-success/5 px-4 py-3 text-sm"
      >
        <CheckCircle2 className="h-4 w-4 shrink-0 text-success" aria-hidden />
        <p className="font-medium">All caught up — no priority items right now.</p>
      </div>
    )
  }

  const sorted = [...priorities].sort(
    (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
  )
  const top = sorted[0]
  const rest = sorted.slice(1, 3)
  const styles = SEVERITY_STYLES[top.severity]
  const Icon = top.severity === "critical" ? AlertTriangle : AlertCircle

  return (
    <div className={cn("rounded-lg border px-4 py-3 text-sm", styles.container)} role="status">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <Icon className={cn("h-4 w-4 shrink-0 translate-y-0.5", styles.icon)} aria-hidden />
          <p className="font-medium">{top.text}</p>
        </div>
        <Link
          href={top.href}
          className="shrink-0 text-sm font-medium text-primary underline-offset-4 hover:underline"
        >
          {top.cta}
          <ArrowRight className="ml-1 inline h-3 w-3" aria-hidden />
        </Link>
      </div>
      {rest.length > 0 ? (
        <ul className="mt-2 space-y-1 pl-7 text-xs text-muted-foreground">
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
    </div>
  )
}
