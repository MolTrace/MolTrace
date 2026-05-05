"use client"

import { Badge } from "@/components/ui/badge"
import type { EvidenceReadinessStatus } from "@/src/lib/spectracheck/evidence-types"
import { cn } from "@/lib/utils"

function labelForReadiness(s: EvidenceReadinessStatus): string {
  switch (s) {
    case "ready_for_unified_evidence":
      return "Ready for Unified Evidence"
    case "usable_with_warnings":
      return "Usable with warnings"
    case "blocked_until_review":
      return "Blocked until review"
    case "not_ready":
      return "Not ready"
    default:
      return s
  }
}

function classForReadiness(s: EvidenceReadinessStatus): string {
  switch (s) {
    case "ready_for_unified_evidence":
      return "border-transparent bg-success/20 text-emerald-950 dark:bg-success/25 dark:text-emerald-50"
    case "usable_with_warnings":
      return "border border-amber-500/50 bg-amber-500/10 text-amber-900 dark:text-amber-100"
    case "blocked_until_review":
      return "border border-violet-500/50 bg-violet-500/10 text-violet-950 dark:text-violet-100"
    case "not_ready":
      return "border border-muted-foreground/35 bg-muted/40 text-muted-foreground"
    default:
      return "border-transparent bg-secondary text-secondary-foreground"
  }
}

export type ReadinessStatusBadgeProps = {
  status: EvidenceReadinessStatus
  className?: string
}

export function ReadinessStatusBadge({ status, className }: ReadinessStatusBadgeProps) {
  return (
    <Badge variant="outline" className={cn("max-w-[220px] truncate font-medium", classForReadiness(status), className)} title={labelForReadiness(status)}>
      {labelForReadiness(status)}
    </Badge>
  )
}
