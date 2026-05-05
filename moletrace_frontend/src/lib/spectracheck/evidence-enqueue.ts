import type { Summary } from "@/components/spectracheck/spectracheck-summary"
import type { AddEvidenceItemInput, EvidenceItemStatus, EvidenceLayerType } from "@/src/lib/spectracheck/evidence-types"
import { extractMethodProvenanceFromUnknown } from "@/src/lib/spectracheck/evidence-method-provenance"
import { extractMlModelProvenanceFromUnknown } from "@/src/lib/ml/model-provenance-extract"

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

export type SpectraCheckUnifiedEvidenceMeta = {
  layer: EvidenceLayerType
  sourceTab: string
  title: string
  endpoint?: string
  sampleId?: string
}

function buildSummaryLine(summary: Summary): string {
  const parts: string[] = []
  if (summary.bestCandidate && summary.bestCandidate !== "Not provided") {
    parts.push(summary.bestCandidate)
  }
  if (summary.confidence !== null) {
    parts.push(`${summary.confidence.toFixed(1)}% score`)
  }
  return parts.length > 0 ? parts.join(" · ") : "Analysis result captured for Unified Evidence."
}

function buildEvidenceSummaryLines(summary: Summary): string[] | undefined {
  const lines: string[] = []
  if (summary.bestCandidate && summary.bestCandidate !== "Not provided") {
    lines.push(summary.bestCandidate)
  }
  if (summary.candidateCount !== null) {
    lines.push(`Candidates: ${summary.candidateCount}`)
  }
  if (summary.evidenceLayers.length > 0) {
    lines.push(`Evidence layers: ${summary.evidenceLayers.slice(0, 12).join(", ")}`)
  }
  return lines.length > 0 ? lines : undefined
}

export function inferEvidenceStatus(response: unknown, summary: Summary): EvidenceItemStatus {
  if (isRecord(response)) {
    if (typeof response.error === "string" && response.error.trim().length > 0) return "error"
    if (response.ok === false) return "error"
    if (typeof response.status === "string" && /^(fail|error)/i.test(response.status)) return "error"
  }
  if (summary.contradictions.length > 0) return "warning"
  if (summary.warnings.length > 0) return "warning"
  if (summary.humanReviewLabel && /review|pending/i.test(summary.humanReviewLabel)) return "pending_review"
  return "ready"
}

export function buildEvidenceItemInput(
  params: SpectraCheckUnifiedEvidenceMeta & {
    response: unknown
    summary: Summary
  },
): AddEvidenceItemInput {
  const { layer, sourceTab, title, sampleId, endpoint, response, summary } = params
  const score = summary.confidence !== null ? summary.confidence : undefined
  const contradictions = summary.contradictions.length > 0 ? [...summary.contradictions] : undefined
  const warnings = summary.warnings.length > 0 ? [...summary.warnings] : undefined
  const notes = summary.notes.length > 0 ? [...summary.notes] : undefined
  const evidenceSummary = buildEvidenceSummaryLines(summary)

  return {
    layer,
    title,
    sourceTab,
    sampleId,
    status: inferEvidenceStatus(response, summary),
    score,
    summary: buildSummaryLine(summary),
    evidenceSummary,
    contradictions,
    warnings,
    notes,
    endpoint,
    response,
    selectedForUnified: true,
    ...extractMethodProvenanceFromUnknown(response),
    ...extractMlModelProvenanceFromUnknown(response),
  }
}
