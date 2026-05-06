import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

export type ReportFilterBucket = "draft" | "review_required" | "approved" | "blocked"

export type SavedReportRow = {
  key: string
  sessionId: string
  /** Numeric report id for collaboration APIs when returned by the backend. */
  reportNumericId: number | null
  /** Numeric SpectraCheck session id when parseable. */
  sessionNumericId: number | null
  reportTitle: string
  sampleId: string
  projectLabel: string
  statusDisplay: string
  reviewer: string
  generatedAt: string
  hashPreview: string
  filterBucket: ReportFilterBucket
  openUrl?: string
  hasJson: boolean
  hasHtml: boolean
  jsonPayload?: unknown
  htmlInline?: string
}

export function normalizeReportsListPayload(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord) as Record<string, unknown>[]
  if (isRecord(data)) {
    if (Array.isArray(data.reports)) return data.reports.filter(isRecord) as Record<string, unknown>[]
    if (Array.isArray(data.items)) return data.items.filter(isRecord) as Record<string, unknown>[]
    if (Array.isArray(data.results)) return data.results.filter(isRecord) as Record<string, unknown>[]
    if (Array.isArray(data.data)) return data.data.filter(isRecord) as Record<string, unknown>[]
  }
  return []
}

export function sessionRecordId(session: Record<string, unknown>): string | null {
  const sid =
    readRecordString(session, "id") ??
    readRecordString(session, "session_id") ??
    readRecordString(session, "sessionId")
  if (sid) return sid
  const n = readRecordNumber(session, "id")
  return n != null ? String(n) : null
}

export function sampleIdFromSession(session: Record<string, unknown>): string {
  return (
    readRecordString(session, "sample_id") ??
    readRecordString(session, "sampleId") ??
    readRecordString(session, "sample_record_id") ??
    "—"
  )
}

function statusTokens(report: Record<string, unknown>): string {
  const parts = [
    readRecordString(report, "status"),
    readRecordString(report, "report_status"),
    readRecordString(report, "release_gate"),
    readRecordString(report, "phase"),
  ].filter(Boolean)
  return parts.join(" ").toLowerCase().replace(/\s+/g, "_").trim()
}

/** Maps backend-style labels to filter buckets without treating generic “ready” as approved. */
export function reportFilterBucket(report: Record<string, unknown>): ReportFilterBucket {
  const s = statusTokens(report)
  if (
    s.includes("blocked_by_contradiction") ||
    s.includes("blocked") ||
    s.includes("insufficient_evidence") ||
    s.includes("contradiction_block")
  ) {
    return "blocked"
  }
  if (s.includes("approved_for_release") || s.includes("released") || s.includes("published")) {
    return "approved"
  }
  if (
    s.includes("review_ready") ||
    s.includes("review_required") ||
    s.includes("pending_review") ||
    s.includes("needs_review") ||
    s.includes("human_review")
  ) {
    return "review_required"
  }
  if (s.includes("draft") || s.includes("generating") || s.includes("in_progress") || s.includes("pending")) {
    return "draft"
  }
  return "draft"
}

function hashPreviewFrom(report: Record<string, unknown>): string {
  const h =
    readRecordString(report, "sha256") ??
    readRecordString(report, "report_hash") ??
    readRecordString(report, "content_sha256") ??
    readRecordString(report, "hash")
  if (!h) return "—"
  return h.length > 18 ? `${h.slice(0, 10)}…${h.slice(-6)}` : h
}

function generatedFrom(report: Record<string, unknown>): string {
  for (const k of ["generated_at", "created_at", "updated_at", "saved_at"]) {
    const t = readRecordString(report, k)
    if (t) {
      const d = Date.parse(t)
      if (!Number.isNaN(d)) return new Date(d).toLocaleString()
      return t
    }
  }
  return "—"
}

function titleFrom(report: Record<string, unknown>): string {
  return (
    readRecordString(report, "report_title") ??
    readRecordString(report, "title") ??
    readRecordString(report, "name") ??
    "Structure elucidation report"
  )
}

function reviewerFrom(report: Record<string, unknown>): string {
  return (
    readRecordString(report, "reviewer_name") ??
    readRecordString(report, "reviewer") ??
    readRecordString(report, "prepared_by") ??
    "—"
  )
}

function statusDisplayFrom(report: Record<string, unknown>): string {
  const raw =
    readRecordString(report, "status") ??
    readRecordString(report, "report_status") ??
    readRecordString(report, "release_gate")
  return raw?.trim() || "—"
}

function reportNumericIdFrom(report: Record<string, unknown>): number | null {
  const n = readRecordNumber(report, "id")
  if (n != null && Number.isFinite(n)) return Math.trunc(n)
  const rs =
    readRecordString(report, "id")?.trim() ??
    readRecordString(report, "report_id")?.trim() ??
    ""
  if (rs && /^\d+$/.test(rs)) {
    const v = parseInt(rs, 10)
    return Number.isFinite(v) ? v : null
  }
  return null
}

function sessionNumericIdFrom(session: Record<string, unknown>): number | null {
  const n = readRecordNumber(session, "id")
  if (n != null && Number.isFinite(n)) return Math.trunc(n)
  return null
}

function openUrlFrom(report: Record<string, unknown>): string | undefined {
  return (
    readRecordString(report, "view_url") ??
    readRecordString(report, "html_url") ??
    readRecordString(report, "report_url") ??
    readRecordString(report, "url")
  )
}

export function buildSavedReportRow(
  session: Record<string, unknown>,
  report: Record<string, unknown>,
  projectById: Map<string, string>,
  index: number,
): SavedReportRow | null {
  const sessionId = sessionRecordId(session)
  if (!sessionId) return null
  const rid =
    readRecordString(report, "id") ??
    readRecordString(report, "report_id") ??
    (readRecordNumber(report, "id") != null ? String(readRecordNumber(report, "id")) : null) ??
    `index-${index}`
  const sampleFromReport =
    readRecordString(report, "sample_id") ?? readRecordString(report, "sampleId")
  const sampleId = sampleFromReport ?? sampleIdFromSession(session)
  const pid =
    readRecordString(session, "project_id") ??
    readRecordString(session, "projectId") ??
    readRecordString(report, "project_id")
  let projectLabel = "—"
  if (pid) {
    projectLabel = projectById.get(String(pid)) ?? pid
  }
  const bucket = reportFilterBucket(report)
  const reportNumericId = reportNumericIdFrom(report)
  const sessionNumericId = sessionNumericIdFrom(session)
  const jsonRaw = report.json_report ?? report.jsonReport
  const jsonPayload =
    jsonRaw != null && (typeof jsonRaw === "object" || typeof jsonRaw === "string") ? jsonRaw : undefined
  const htmlInline =
    typeof report.html_report === "string"
      ? report.html_report
      : typeof report.htmlReport === "string"
        ? report.htmlReport
        : undefined
  const hasJson = jsonPayload != null
  const hasHtml = Boolean(htmlInline) || Boolean(openUrlFrom(report))

  return {
    key: `${sessionId}:${rid}`,
    sessionId,
    reportNumericId,
    sessionNumericId,
    reportTitle: titleFrom(report),
    sampleId,
    projectLabel,
    statusDisplay: statusDisplayFrom(report),
    reviewer: reviewerFrom(report),
    generatedAt: generatedFrom(report),
    hashPreview: hashPreviewFrom(report),
    filterBucket: bucket,
    openUrl: openUrlFrom(report),
    hasJson,
    hasHtml,
    jsonPayload: hasJson ? jsonPayload : undefined,
    htmlInline,
  }
}
