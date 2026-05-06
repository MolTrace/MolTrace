"use client"

import type { ReactNode } from "react"
import { cn } from "@/lib/utils"
import {
  hasRenderableMlRegistryProvenance,
  mergeMlModelProvenancePreferItem,
  type MlModelProvenanceFields,
} from "@/src/lib/ml/model-provenance-extract"

export type MlModelProvenanceSummaryProps = {
  /** Raw API fragments (responses, nested answer objects, rows). Order: later overrides earlier unless using itemFields. */
  sources: unknown[]
  /** Prefer values already merged onto EvidenceItem-shaped objects */
  itemFields?: Partial<MlModelProvenanceFields>
  /** Optional human-review lines (e.g. regulatory answer) shown after registry lines when present */
  humanReviewExtras?: ReactNode
  /** Tailwind wrapper */
  className?: string
  /** Typography for missing line */
  missingClassName?: string
}

function line(label: string, value: string | number | undefined | null): ReactNode {
  if (value === undefined || value === null || value === "") return null
  return (
    <p className="text-[11px] text-muted-foreground">
      <span className="font-mono text-foreground/80">{label}: </span>
      <span className="break-all">{String(value)}</span>
    </p>
  )
}

export function MlModelProvenanceSummary({
  sources,
  itemFields,
  humanReviewExtras,
  className,
  missingClassName = "text-[11px] text-muted-foreground",
}: MlModelProvenanceSummaryProps) {
  const merged = mergeMlModelProvenancePreferItem(itemFields ?? {}, ...sources)

  if (!hasRenderableMlRegistryProvenance(merged)) {
    return (
      <div className={className}>
        <p className={missingClassName}>Model provenance not recorded for this result.</p>
        {humanReviewExtras}
      </div>
    )
  }

  const nameVer =
    merged.modelName || merged.modelVersion
      ? [merged.modelName, merged.modelVersion].filter(Boolean).join(" · ")
      : ""

  return (
    <div className={cn("space-y-0.5", className)}>
      <div className="flex flex-wrap items-center gap-1">
        <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          ML model provenance
        </span>
      </div>
      {line("model_artifact_id", merged.modelArtifactId)}
      {nameVer ? line("model name / version", nameVer) : null}
      {line("method_id", merged.methodId)}
      {line("dataset_version_id", merged.datasetVersionId)}
      {line("evaluation_run_id", merged.evaluationRunId)}
      {line("deployment_candidate_id", merged.deploymentCandidateId)}
      {line("model_card_id", merged.modelCardId)}
      {line("approval_status", merged.approvalStatus)}
      {humanReviewExtras}
    </div>
  )
}
