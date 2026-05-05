"use client"

import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { QualityStatusBadge, type QualityGateStatus } from "@/src/components/spectracheck/QualityStatusBadge"
import { cn } from "@/lib/utils"

const QC_TITLE_TOOLTIP =
  "Quality control checks whether uploaded files, artifacts, and evidence records are reliable enough to be used in Unified Evidence. QC does not confirm molecular identity."

export type QualityAssessmentCardProps = {
  qcStatus: QualityGateStatus
  /** Readiness label from orchestration (e.g. ready / blocked / needs_inputs). */
  readinessLabel: string
  /** Normalized 0–1 or backend scale; pass null if unknown. */
  qualityScore: number | null
  targetType: string
  modality: string
  warningsCount: number
  findingsCount: number
  recommendedActions: readonly string[]
  /** When true, show override affordance (blocked or requires review). */
  showOverride: boolean
  onRunQc?: () => void
  onViewFindings?: () => void
  onOpenOverride?: () => void
  developerJson?: unknown
  runQcBusy?: boolean
  className?: string
}

export function QualityAssessmentCard({
  qcStatus,
  readinessLabel,
  qualityScore,
  targetType,
  modality,
  warningsCount,
  findingsCount,
  recommendedActions,
  showOverride,
  onRunQc,
  onViewFindings,
  onOpenOverride,
  developerJson,
  runQcBusy = false,
  className,
}: QualityAssessmentCardProps) {
  return (
    <Card className={cn("min-w-0 border-muted", className)}>
      <CardHeader className="pb-2">
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          Quality control &amp; evidence readiness
          <span
            className="inline-flex shrink-0"
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
            }}
          >
            <InfoTooltip label="About quality control" content={QC_TITLE_TOOLTIP} className="size-4" />
          </span>
        </CardTitle>
        <CardDescription>
          Assess whether inputs are usable as evidence in Unified Evidence. This does not validate chemical identity.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">QC status</span>
          <QualityStatusBadge status={qcStatus} />
        </div>
        <div className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <p className="text-xs font-medium text-muted-foreground">Readiness</p>
            <p className="font-medium">{readinessLabel}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground">Quality score</p>
            <p className="font-mono">{qualityScore != null ? qualityScore.toFixed(3) : "—"}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground">Target type</p>
            <p>{targetType}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground">Modality</p>
            <p>{modality}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground">Warnings</p>
            <p className="font-mono">{warningsCount}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground">Findings</p>
            <p className="font-mono">{findingsCount}</p>
          </div>
        </div>

        <div>
          <p className="text-xs font-medium text-muted-foreground">Recommended actions</p>
          {recommendedActions.length === 0 ? (
            <p className="mt-1 text-sm text-muted-foreground">—</p>
          ) : (
            <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-muted-foreground">
              {recommendedActions.map((line, i) => (
                <li key={`${i}-${line.slice(0, 24)}`}>{line}</li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" disabled={runQcBusy} onClick={() => onRunQc?.()}>
            {runQcBusy ? "Running QC…" : "Run QC"}
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={() => onViewFindings?.()}>
            View findings
          </Button>
          {showOverride && onOpenOverride ? (
            <Button type="button" size="sm" variant="secondary" onClick={() => onOpenOverride()}>
              Override
            </Button>
          ) : null}
        </div>

        {developerJson !== undefined ? <DeveloperJsonPanel data={developerJson} /> : null}
      </CardContent>
    </Card>
  )
}

/** Example props for integration tests or manual preview. */
export const MOCK_QUALITY_ASSESSMENT_PROPS: QualityAssessmentCardProps = {
  qcStatus: "qc_warning",
  readinessLabel: "Conditionally usable as evidence",
  qualityScore: 0.72,
  targetType: "spectracheck_session",
  modality: "multimodal_nmr_ms",
  warningsCount: 2,
  findingsCount: 2,
  recommendedActions: [
    "Re-verify file digests for uploaded raw data.",
    "Confirm MS/MS layer coverage before synthesis.",
  ],
  showOverride: true,
  developerJson: { mock: true, qc_run_id: "qc-demo-001" },
}
