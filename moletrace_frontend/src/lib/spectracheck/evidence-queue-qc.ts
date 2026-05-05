/**
 * Evidence Queue QC gate: readiness derivation and assessment mapping.
 * Does not rename API request paths or fields.
 */

import type { EvidenceItem } from "@/src/lib/spectracheck/evidence-types"
import type { EvidenceQcStatus, EvidenceReadinessStatus } from "@/src/lib/spectracheck/evidence-types"
import {
  parseQualityControlPayload,
  parseSessionQualityControlPayload,
  type ParsedSessionQualityControl,
} from "@/src/lib/spectracheck/quality-control-assessment"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(o: Record<string, unknown>, keys: string[]): string | null {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "string" && v.trim()) return v.trim()
    if (typeof v === "number" && Number.isFinite(v)) return String(v)
  }
  return null
}

function parseReadinessEnum(s: string | null): EvidenceReadinessStatus | undefined {
  if (!s) return undefined
  const x = s.trim().toLowerCase().replace(/-/g, "_")
  if (
    x === "ready_for_unified_evidence" ||
    x === "ready" ||
    x === "passed"
  )
    return "ready_for_unified_evidence"
  if (x === "usable_with_warnings" || x === "warning" || x === "conditional") return "usable_with_warnings"
  if (
    x === "blocked_until_review" ||
    x === "blocked" ||
    x === "needs_review" ||
    x === "requires_review"
  )
    return "blocked_until_review"
  if (x === "not_ready" || x === "not_assessed" || x === "pending") return "not_ready"
  return undefined
}

/** Pull readiness_status / readiness from assessment payloads when present. */
export function extractEvidenceReadinessFromPayload(raw: unknown): EvidenceReadinessStatus | undefined {
  if (!isRecord(raw)) return undefined
  const direct =
    readStr(raw, ["readiness_status", "readinessStatus", "readiness", "evidence_readiness"]) ??
    (isRecord(raw.assessment)
      ? readStr(raw.assessment, ["readiness_status", "readinessStatus", "readiness"])
      : null)
  return parseReadinessEnum(direct)
}

export function extractQualityAssessmentId(raw: unknown): string | undefined {
  if (!isRecord(raw)) return undefined
  const id =
    readStr(raw, ["quality_assessment_id", "qualityAssessmentId", "assessment_id", "assessmentId", "id"]) ??
    (isRecord(raw.assessment)
      ? readStr(raw.assessment, ["quality_assessment_id", "assessment_id", "id"])
      : null)
  return id ?? undefined
}

/** Merge parsed QC payload into EvidenceItem patch fields. */
export function mapAssessmentResponseToEvidencePatch(raw: unknown): Partial<EvidenceItem> {
  const p = parseQualityControlPayload(raw, { targetType: "evidence_item", modality: "spectracheck_evidence" })
  const readinessFromApi = extractEvidenceReadinessFromPayload(raw)
  const qcStatus = p.qcStatus as EvidenceQcStatus
  const readinessStatus: EvidenceReadinessStatus =
    readinessFromApi ??
    deriveReadinessFromQcAndLabel(qcStatus, p.readinessLabel)

  return {
    qualityAssessmentId: extractQualityAssessmentId(raw),
    qcStatus,
    readinessStatus,
  }
}

function deriveReadinessFromQcAndLabel(qc: EvidenceQcStatus, readinessLabel: string): EvidenceReadinessStatus {
  const fromLabel = parseReadinessEnum(readinessLabel.toLowerCase())
  if (fromLabel) return fromLabel
  switch (qc) {
    case "qc_pass":
      return "ready_for_unified_evidence"
    case "qc_warning":
      return "usable_with_warnings"
    case "requires_human_review":
      return "blocked_until_review"
    case "qc_fail":
      return "not_ready"
    case "not_assessed":
      return "not_ready"
    default:
      return "not_ready"
  }
}

function humanReviewResolved(item: EvidenceItem): boolean {
  return Boolean(item.overrideReason?.trim() && item.overrideStatus?.trim())
}

function qcFailAllowlisted(item: EvidenceItem): boolean {
  return item.overrideStatus === "allow_with_warning" && Boolean(item.overrideReason?.trim())
}

/**
 * Effective readiness for gating (uses persisted readiness when set; otherwise derives from qc + overrides).
 */
export function effectiveEvidenceReadiness(item: EvidenceItem): EvidenceReadinessStatus {
  if (item.readinessStatus) return item.readinessStatus
  const q: EvidenceQcStatus = item.qcStatus ?? "not_assessed"
  if (q === "not_assessed") return "not_ready"
  if (q === "qc_pass") return "ready_for_unified_evidence"
  if (q === "qc_warning") return "usable_with_warnings"
  if (q === "requires_human_review") {
    if (humanReviewResolved(item)) return "ready_for_unified_evidence"
    return "blocked_until_review"
  }
  if (q === "qc_fail") {
    if (qcFailAllowlisted(item)) return "usable_with_warnings"
    return "not_ready"
  }
  return "not_ready"
}

/** True when this row must not proceed to Unified Evidence without QC or override (selected flow gate). */
export function isUnifiedSendBlocked(item: EvidenceItem): boolean {
  const r = effectiveEvidenceReadiness(item)
  return r === "blocked_until_review" || r === "not_ready"
}

/** Apply reviewer override from dialog (requires reason + reviewer via payload). */
export function patchEvidenceAfterOverride(
  item: EvidenceItem,
  payload: { reviewerName: string; decision: "allow_with_warning" | "block" | "needs_reprocessing"; reason: string },
): Partial<EvidenceItem> {
  const overrideReason = `[${payload.reviewerName}] ${payload.reason}`.trim()
  const base: Partial<EvidenceItem> = {
    overrideStatus: payload.decision,
    overrideReason,
  }
  if (payload.decision === "allow_with_warning") {
    if (item.qcStatus === "qc_fail") return { ...base, readinessStatus: "usable_with_warnings" }
    if (item.qcStatus === "requires_human_review") return { ...base, readinessStatus: "ready_for_unified_evidence" }
    return { ...base, readinessStatus: "usable_with_warnings" }
  }
  if (payload.decision === "needs_reprocessing") return { ...base, readinessStatus: "not_ready" }
  return { ...base, readinessStatus: "blocked_until_review" }
}

/** Unified Evidence tab: readiness gate summary for selected queue rows (override-aware). */
export function summarizeUnifiedEvidenceQueueQc(selected: EvidenceItem[]): {
  blocked_items: Array<{
    id: string
    title: string
    readiness_status: EvidenceReadinessStatus
    qc_status: EvidenceQcStatus | undefined
  }>
  aggregate_warnings: string[]
  items_with_override: Array<{
    id: string
    title: string
    override_status: string | undefined
    override_reason: string | undefined
  }>
  human_review_required: boolean
  gate_blocks_build: boolean
} {
  const blocked_items = selected
    .filter(isUnifiedSendBlocked)
    .map((i) => ({
      id: i.id,
      title: i.title,
      readiness_status: effectiveEvidenceReadiness(i),
      qc_status: i.qcStatus,
    }))
  const aggregate_warnings = Array.from(new Set(selected.flatMap((i) => i.warnings ?? [])))
  const items_with_override = selected
    .filter((i) => Boolean(i.overrideReason?.trim() || i.overrideStatus?.trim()))
    .map((i) => ({
      id: i.id,
      title: i.title,
      override_status: i.overrideStatus,
      override_reason: i.overrideReason,
    }))
  const human_review_required = selected.some(
    (i) =>
      effectiveEvidenceReadiness(i) === "usable_with_warnings" ||
      i.qcStatus === "qc_warning" ||
      Boolean(i.overrideReason?.trim()) ||
      (i.warnings?.length ?? 0) > 0,
  )
  return {
    blocked_items,
    aggregate_warnings,
    items_with_override,
    human_review_required,
    gate_blocks_build: blocked_items.length > 0,
  }
}

export type QcProvenanceSectionPayload = {
  report_language: {
    evidence_quality_reviewed: string
    usable_with_warnings: string
    requires_human_review: string
  }
  narrative_key: "evidence_quality_reviewed" | "usable_with_warnings" | "requires_human_review"
  session_qc: ParsedSessionQualityControl | null
  evidence_qc_rows: Array<{
    id: string
    title: string
    qc_status: EvidenceQcStatus | null
    readiness_status: EvidenceReadinessStatus
    quality_assessment_id: string | null
    override_status: string | null
    override_reason: string | null
  }>
  failed_or_overridden_evidence: Array<{ title: string; layer: string; detail: string }>
  reviewer_override_reasons: string[]
  recommended_actions: string[]
  source_file_sha256_list: string[]
  human_review_suggested: boolean
}

/** Report composer provenance JSON: session QC + selected evidence QC without renaming API-facing evidence fields. */
export function buildQcProvenanceForReport(args: {
  sessionQcRaw: unknown | null
  selectedEvidence: EvidenceItem[]
  sourceFileSha256List: string[]
}): QcProvenanceSectionPayload {
  const session_qc =
    args.sessionQcRaw != null ? parseSessionQualityControlPayload(args.sessionQcRaw) : null

  const evidence_qc_rows = args.selectedEvidence.map((i) => ({
    id: i.id,
    title: i.title,
    qc_status: i.qcStatus ?? null,
    readiness_status: effectiveEvidenceReadiness(i),
    quality_assessment_id: i.qualityAssessmentId ?? null,
    override_status: i.overrideStatus ?? null,
    override_reason: i.overrideReason?.trim() ? i.overrideReason.trim() : null,
  }))

  const failed_or_overridden_evidence = args.selectedEvidence
    .filter(
      (i) =>
        i.qcStatus === "qc_fail" ||
        Boolean(i.overrideReason?.trim()) ||
        effectiveEvidenceReadiness(i) === "not_ready" ||
        effectiveEvidenceReadiness(i) === "blocked_until_review",
    )
    .map((i) => ({
      title: i.title,
      layer: i.layer,
      detail: [
        i.qcStatus && `qc: ${i.qcStatus}`,
        `readiness: ${effectiveEvidenceReadiness(i)}`,
        i.overrideReason?.trim() && `override: ${i.overrideReason}`,
      ]
        .filter(Boolean)
        .join(" · "),
    }))

  const reviewer_override_reasons = args.selectedEvidence
    .map((i) => i.overrideReason?.trim())
    .filter((x): x is string => Boolean(x))

  const recommended_actions = session_qc?.recommendedActions ?? []

  const human_review_suggested = args.selectedEvidence.some(
    (i) =>
      effectiveEvidenceReadiness(i) === "usable_with_warnings" ||
      i.qcStatus === "qc_warning" ||
      Boolean(i.overrideReason?.trim()) ||
      (i.warnings?.length ?? 0) > 0,
  )

  let narrative_key: QcProvenanceSectionPayload["narrative_key"]
  if (human_review_suggested) narrative_key = "requires_human_review"
  else if (
    (session_qc?.warnings ?? 0) > 0 ||
    (session_qc?.failed ?? 0) > 0 ||
    args.selectedEvidence.some((i) => i.qcStatus === "requires_human_review")
  )
    narrative_key = "usable_with_warnings"
  else narrative_key = "evidence_quality_reviewed"

  return {
    report_language: {
      evidence_quality_reviewed: "Evidence quality reviewed",
      usable_with_warnings: "Usable with warnings",
      requires_human_review: "Requires human review",
    },
    narrative_key,
    session_qc,
    evidence_qc_rows,
    failed_or_overridden_evidence,
    reviewer_override_reasons,
    recommended_actions,
    source_file_sha256_list: args.sourceFileSha256List,
    human_review_suggested,
  }
}
