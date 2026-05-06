/**
 * Report lock API — paths and body fields match backend contracts.
 */

import { ApiError, apiFetch } from "@/lib/api/client"

export type ReportLockDisplayStatus = "unlocked" | "locked" | "released"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

export function normalizeApprovalsList(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord) as Record<string, unknown>[]
  if (isRecord(data)) {
    if (Array.isArray(data.approvals)) return data.approvals.filter(isRecord) as Record<string, unknown>[]
    if (Array.isArray(data.items)) return data.items.filter(isRecord) as Record<string, unknown>[]
    if (Array.isArray(data.results)) return data.results.filter(isRecord) as Record<string, unknown>[]
  }
  return []
}

/** Backend gate for release: approval decision approved_confirmed scoped to session/report. */
export function hasApprovedConfirmedForReport(
  approvals: Record<string, unknown>[],
  reportId: number,
): boolean {
  return approvals.some((a) => {
    const dec = a.decision ?? a.decision_type
    if (String(dec) !== "approved_confirmed") return false
    const rid = a.report_id ?? a.reportId
    if (rid == null || rid === "") return true
    return Number(rid) === reportId
  })
}

export function lockRecordDisplayStatus(
  record: Record<string, unknown> | null,
): ReportLockDisplayStatus {
  if (!record) return "unlocked"
  const s = record.status
  if (s === "locked" || s === "unlocked" || s === "released") return s
  return "unlocked"
}

export async function fetchReportLockRecord(reportId: number): Promise<Record<string, unknown> | null> {
  try {
    const data = await apiFetch<unknown>(`/reports/${encodeURIComponent(String(reportId))}/lock`, {
      method: "GET",
    })
    return isRecord(data) ? data : null
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null
    throw err
  }
}

export async function fetchSessionApprovals(sessionId: string): Promise<Record<string, unknown>[]> {
  const sid = sessionId.trim()
  if (!sid) return []
  const data = await apiFetch<unknown>(
    `/spectracheck/sessions/${encodeURIComponent(sid)}/approvals`,
    { method: "GET" },
  )
  return normalizeApprovalsList(data)
}

export type ReportLockPostBody = {
  session_id?: number
  locked_by?: string | null
  lock_reason?: string | null
  metadata_json?: Record<string, unknown>
}

export type ReportReleasePostBody = {
  override_approval_requirement?: boolean
  rationale?: string | null
  metadata_json?: Record<string, unknown>
}

export async function postReportLock(reportId: number, body: ReportLockPostBody): Promise<Record<string, unknown>> {
  const data = await apiFetch<unknown>(`/reports/${encodeURIComponent(String(reportId))}/lock`, {
    method: "POST",
    body,
  })
  return isRecord(data) ? data : {}
}

export async function postReportUnlock(reportId: number, body: ReportLockPostBody): Promise<Record<string, unknown>> {
  const data = await apiFetch<unknown>(`/reports/${encodeURIComponent(String(reportId))}/unlock`, {
    method: "POST",
    body,
  })
  return isRecord(data) ? data : {}
}

export async function postReportRelease(
  reportId: number,
  body: ReportReleasePostBody,
): Promise<Record<string, unknown>> {
  const data = await apiFetch<unknown>(`/reports/${encodeURIComponent(String(reportId))}/release`, {
    method: "POST",
    body,
  })
  return isRecord(data) ? data : {}
}
