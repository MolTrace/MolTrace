"use client"

import { Badge } from "@/components/ui/badge"
import type { QcGateStatus } from "@/src/lib/spectracheck/quality-control-assessment"
import { cn } from "@/lib/utils"

/** QC / readiness gate label returned by orchestration (display-only mapping). */
export type QualityGateStatus = QcGateStatus

function labelForStatus(status: QualityGateStatus): string {
  switch (status) {
    case "qc_pass":
      return "QC pass"
    case "qc_warning":
      return "QC warning"
    case "qc_fail":
      return "QC fail"
    case "requires_human_review":
      return "Requires human review"
    case "not_assessed":
      return "Not assessed"
    default:
      return status
  }
}

function classForStatus(status: QualityGateStatus): string {
  switch (status) {
    case "qc_pass":
      return "border-transparent bg-success/20 text-emerald-950 dark:bg-success/25 dark:text-emerald-50"
    case "qc_warning":
      return "border border-amber-500/50 bg-amber-500/10 text-amber-900 dark:text-amber-100"
    case "qc_fail":
      return "border-transparent bg-destructive text-white dark:bg-destructive/60"
    case "requires_human_review":
      return "border border-violet-500/50 bg-violet-500/10 text-violet-950 dark:text-violet-100"
    case "not_assessed":
      return "border border-muted-foreground/35 bg-muted/40 text-muted-foreground"
    default:
      return "border-transparent bg-secondary text-secondary-foreground"
  }
}

export type QualityStatusBadgeProps = {
  status: QualityGateStatus
  className?: string
}

export function QualityStatusBadge({ status, className }: QualityStatusBadgeProps) {
  return (
    <Badge variant="outline" className={cn("font-medium", classForStatus(status), className)}>
      {labelForStatus(status)}
    </Badge>
  )
}
