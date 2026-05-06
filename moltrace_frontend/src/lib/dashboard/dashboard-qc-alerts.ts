/**
 * Dashboard-wide QC alert aggregation from GET /quality-control/sessions/{session_id}
 * (session list comes from GET /spectracheck/sessions). Does not rename API fields.
 */

import { apiFetch } from "@/lib/api/client"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { parseSessionQualityControlPayload } from "@/src/lib/spectracheck/quality-control-assessment"

/** Same id resolution as overview metrics session rows. */
export function spectracheckSessionRowId(s: Record<string, unknown>): string {
  const sid =
    readRecordString(s, "id") ??
    readRecordString(s, "session_id") ??
    readRecordString(s, "sessionId")
  if (sid) return sid
  const n = readRecordNumber(s, "id")
  return n != null ? String(n) : ""
}

function sessionUpdatedAtMs(s: Record<string, unknown>): number {
  for (const k of ["updated_at", "modified_at", "saved_at", "created_at", "last_saved_at"]) {
    const t = readRecordString(s, k)
    if (t) {
      const d = Date.parse(t)
      if (!Number.isNaN(d)) return d
    }
  }
  return 0
}

export function sortSessionsNewestFirst(sessions: Record<string, unknown>[]): Record<string, unknown>[] {
  return [...sessions].sort((a, b) => sessionUpdatedAtMs(b) - sessionUpdatedAtMs(a))
}

function sampleLabelForSessionRow(row: Record<string, unknown>): string {
  return (
    readRecordString(row, "sample_id") ??
    readRecordString(row, "sampleId") ??
    readRecordString(row, "sample_record_id") ??
    spectracheckSessionRowId(row) ??
    "—"
  )
}

function sessionRowNeedsQcReview(parsed: ReturnType<typeof parseSessionQualityControlPayload>): boolean {
  if ((parsed.requiresReview ?? 0) > 0) return true
  if ((parsed.failed ?? 0) > 0) return true
  const r = parsed.sessionReadiness.toLowerCase()
  return (
    r.includes("review") ||
    r.includes("blocked") ||
    r.includes("human") ||
    r.includes("requires_human") ||
    r.includes("needs_review")
  )
}

export type DashboardRecentFailedQcRow = {
  session_id: string
  session_label: string
  title: string
  message: string
}

export type DashboardQcAlertsAggregate = {
  qc_warnings_count: number
  qc_failures_count: number
  sessions_requiring_qc_review: number
  recent_failed_qc_items: DashboardRecentFailedQcRow[]
}

const MAX_SESSIONS_QC_SCAN = 18

/**
 * Fetches QC summaries for the most recently updated sessions and aggregates counts.
 * Returns `available: false` when every request fails (endpoint missing or errors).
 */
export async function fetchDashboardQcAlertsAggregate(
  sessions: Record<string, unknown>[],
): Promise<{ available: boolean; aggregate: DashboardQcAlertsAggregate }> {
  const sorted = sortSessionsNewestFirst(sessions).slice(0, MAX_SESSIONS_QC_SCAN)
  if (sorted.length === 0) {
    return {
      available: true,
      aggregate: {
        qc_warnings_count: 0,
        qc_failures_count: 0,
        sessions_requiring_qc_review: 0,
        recent_failed_qc_items: [],
      },
    }
  }

  const settled = await Promise.allSettled(
    sorted.map(async (row) => {
      const id = spectracheckSessionRowId(row)
      if (!id.trim()) throw new Error("missing session id")
      const raw = await apiFetch<unknown>(`/quality-control/sessions/${encodeURIComponent(id)}`, {
        method: "GET",
      })
      return { row, id, raw }
    }),
  )

  let anySuccess = false
  let qcWarningsCount = 0
  let qcFailuresCount = 0
  let sessionsRequiringQcReview = 0
  const recentFailedQcItems: DashboardRecentFailedQcRow[] = []

  for (const s of settled) {
    if (s.status !== "fulfilled") continue
    const { row, id, raw } = s.value
    anySuccess = true
    const parsed = parseSessionQualityControlPayload(raw)
    qcWarningsCount += parsed.warnings ?? 0
    qcFailuresCount += parsed.failed ?? 0
    if (sessionRowNeedsQcReview(parsed)) sessionsRequiringQcReview += 1

    const session_label = sampleLabelForSessionRow(row)
    for (const f of parsed.findings) {
      if (f.severity === "error") {
        recentFailedQcItems.push({
          session_id: id,
          session_label,
          title: f.title,
          message: f.message,
        })
      }
    }
  }

  return {
    available: anySuccess,
    aggregate: {
      qc_warnings_count: qcWarningsCount,
      qc_failures_count: qcFailuresCount,
      sessions_requiring_qc_review: sessionsRequiringQcReview,
      recent_failed_qc_items: recentFailedQcItems.slice(0, 8),
    },
  }
}
