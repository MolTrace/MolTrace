/**
 * Maps quality-control API payloads to UI-ready shapes without renaming API fields when reading.
 */

/** Portable QC finding row (same shape as `QualityFindingsTable` rows). */
export type QcFindingSeverity = "error" | "warning" | "info"

export type QcFindingRow = {
  severity: QcFindingSeverity
  code: string
  title: string
  message: string
  recommendation: string
  layer: string
}

/** Portable QC gate label for badges (same values as `QualityStatusBadge`). */
export type QcGateStatus =
  | "qc_pass"
  | "qc_warning"
  | "qc_fail"
  | "requires_human_review"
  | "not_assessed"

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

function readNum(o: Record<string, unknown>, keys: string[]): number | null {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "number" && Number.isFinite(v)) return v
    if (typeof v === "string") {
      const n = Number(v)
      if (Number.isFinite(n)) return n
    }
  }
  return null
}

/** Normalize backend qc_status / status strings to badge union. */
export function normalizeQualityGateStatus(raw: unknown): QcGateStatus {
  const s =
    typeof raw === "string"
      ? raw
      : typeof raw === "number"
        ? String(raw)
        : ""
  const x = s.trim().toLowerCase().replace(/-/g, "_")
  if (!x) return "not_assessed"
  if (x === "qc_pass" || x === "pass" || x === "passed" || x === "ok") return "qc_pass"
  if (x === "qc_warning" || x === "warning" || x === "warn") return "qc_warning"
  if (x === "qc_fail" || x === "fail" || x === "failed" || x === "error" || x === "blocked") return "qc_fail"
  if (x === "requires_human_review" || x === "human_review" || x === "needs_review") return "requires_human_review"
  if (x === "not_assessed" || x === "unknown" || x === "pending") return "not_assessed"
  return "not_assessed"
}

function pickRoot(raw: unknown): Record<string, unknown> {
  if (!isRecord(raw)) return {}
  const nested =
    isRecord(raw.assessment) ? raw.assessment : isRecord(raw.result) ? raw.result : isRecord(raw.data) ? raw.data : null
  return nested ?? raw
}

function normalizeSeverity(raw: unknown): QcFindingSeverity {
  const s = typeof raw === "string" ? raw.toLowerCase() : ""
  if (s === "error" || s === "critical" || s === "fail") return "error"
  if (s === "warning" || s === "warn") return "warning"
  return "info"
}

function parseFindingRow(item: unknown): QcFindingRow | null {
  if (!isRecord(item)) return null
  return {
    severity: normalizeSeverity(
      item.severity ?? item.level ?? item.rank ?? item.priority,
    ),
    code: readStr(item, ["code", "finding_code", "id", "key"]) ?? "—",
    title: readStr(item, ["title", "name", "label", "summary"]) ?? "—",
    message: readStr(item, ["message", "detail", "description", "text"]) ?? "—",
    recommendation: readStr(item, ["recommendation", "recommended_action", "remediation", "fix"]) ?? "—",
    layer: readStr(item, ["layer", "source_layer", "evidence_layer", "scope"]) ?? "—",
  }
}

function parseFindingsList(raw: unknown): QcFindingRow[] {
  if (!Array.isArray(raw)) return []
  const out: QcFindingRow[] = []
  for (const item of raw) {
    const row = parseFindingRow(item)
    if (row) out.push(row)
  }
  return out
}

function parseRecommendedActions(raw: unknown): string[] {
  if (!Array.isArray(raw)) return []
  const out: string[] = []
  for (const x of raw) {
    if (typeof x === "string" && x.trim()) out.push(x.trim())
    else if (isRecord(x)) {
      const t = readStr(x, ["text", "message", "action", "label", "title"])
      if (t) out.push(t)
    }
  }
  return out
}

export type ParsedQualityAssessment = {
  qcStatus: QcGateStatus
  readinessLabel: string
  qualityScore: number | null
  targetType: string
  modality: string
  warningsCount: number
  findingsCount: number
  recommendedActions: string[]
  showOverride: boolean
  findings: QcFindingRow[]
}

/**
 * Interpret GET /quality-control/files/{id} or POST .../assess response (or nested assessment objects).
 */
export function parseQualityControlPayload(
  raw: unknown,
  defaults: { targetType: string; modality: string },
): ParsedQualityAssessment {
  const root = pickRoot(raw)
  const qcRaw =
    root.qc_status ??
    root.qcStatus ??
    root.status ??
    (isRecord(root.quality) ? root.quality.qc_status : undefined)
  const qcStatus = normalizeQualityGateStatus(qcRaw)

  const readinessLabel =
    readStr(root, [
      "readiness_status",
      "readinessStatus",
      "readiness_label",
      "readinessLabel",
      "readiness",
      "evidence_readiness",
    ]) ??
    (qcStatus === "not_assessed" ? "Not assessed" : "See QC status")

  const qualityScore = readNum(root, ["quality_score", "qualityScore", "overall_score", "score"])

  const targetType =
    readStr(root, ["target_type", "targetType", "resource_type", "kind"]) ?? defaults.targetType
  const modality = readStr(root, ["modality", "modalities", "domain"]) ?? defaults.modality

  const warningsRaw = root.warnings
  const warningsCount = Array.isArray(warningsRaw)
    ? warningsRaw.length
    : readNum(root, ["warnings_count", "warningsCount", "warning_count"]) ?? 0

  const findingsRaw =
    root.findings ??
    root.qc_findings ??
    root.issues ??
    (isRecord(root.assessment) ? root.assessment.findings : undefined)
  const findings = parseFindingsList(findingsRaw)
  const findingsCount =
    readNum(root, ["findings_count", "findingsCount", "issue_count"]) ?? findings.length

  const recommendedActions =
    parseRecommendedActions(
      root.recommended_actions ?? root.recommendedActions ?? root.actions ?? root.recommendations,
    )

  const showOverride = qcStatus === "qc_fail" || qcStatus === "requires_human_review"

  return {
    qcStatus,
    readinessLabel,
    qualityScore,
    targetType,
    modality,
    warningsCount,
    findingsCount,
    recommendedActions,
    showOverride,
    findings,
  }
}

/** Session-level GET/POST /quality-control/sessions/{id} payload (counts vary by backend; keys read defensively). */
export type ParsedSessionQualityControl = {
  totalAssessed: number | null
  qcPassed: number | null
  warnings: number | null
  failed: number | null
  requiresReview: number | null
  sessionReadiness: string
  recommendedActions: string[]
  findings: QcFindingRow[]
}

function countFromRecords(o: Record<string, unknown>, keys: string[]): number | null {
  for (const k of keys) {
    const n = readNum(o, [k])
    if (n != null) return n
  }
  return null
}

/**
 * Interpret GET or POST responses for `/quality-control/sessions/{session_id}` without renaming API fields.
 */
export function parseSessionQualityControlPayload(raw: unknown): ParsedSessionQualityControl {
  const root = pickRoot(raw)
  const counts =
    isRecord(root.counts) ? root.counts : isRecord(root.summary) ? root.summary : isRecord(root.totals) ? root.totals : root

  const totalAssessed =
    countFromRecords(counts as Record<string, unknown>, [
      "total_assessed_items",
      "total_assessed",
      "assessed_count",
      "items_assessed",
      "total_items_assessed",
      "assessed",
    ]) ?? countFromRecords(root, ["total_assessed_items", "total_assessed", "assessed_count"])

  const qcPassed =
    countFromRecords(counts as Record<string, unknown>, [
      "qc_passed",
      "qc_pass",
      "passed",
      "pass_count",
      "qc_pass_count",
    ]) ?? countFromRecords(root, ["qc_passed", "qc_pass_count"])

  const warnings =
    countFromRecords(counts as Record<string, unknown>, [
      "warnings",
      "qc_warning",
      "warning_count",
      "warnings_count",
      "qc_warnings",
    ]) ?? countFromRecords(root, ["warnings_count", "qc_warning_count"])

  const failed =
    countFromRecords(counts as Record<string, unknown>, [
      "failed",
      "qc_fail",
      "fail_count",
      "qc_failed",
      "failures",
    ]) ?? countFromRecords(root, ["failed_count", "qc_fail_count"])

  const requiresReview =
    countFromRecords(counts as Record<string, unknown>, [
      "requires_human_review",
      "requires_review",
      "human_review",
      "needs_review",
      "review_required",
    ]) ?? countFromRecords(root, ["requires_human_review_count", "requires_review_count"])

  const sessionReadiness =
    readStr(root, [
      "session_readiness",
      "sessionReadiness",
      "readiness_status",
      "readinessStatus",
      "session_readiness_status",
      "evidence_readiness",
      "readiness_label",
    ]) ?? "—"

  const findingsRaw =
    root.findings ??
    root.session_findings ??
    root.qc_findings ??
    (isRecord(root.assessment) ? root.assessment.findings : undefined)

  const findings = parseFindingsList(findingsRaw)

  const recommendedActions = parseRecommendedActions(
    root.recommended_actions ?? root.recommendedActions ?? root.actions ?? root.recommendations,
  )

  return {
    totalAssessed,
    qcPassed,
    warnings,
    failed,
    requiresReview,
    sessionReadiness,
    recommendedActions,
    findings,
  }
}
