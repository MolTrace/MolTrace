/**
 * Review task queue — uses session-scoped list endpoints; no global catalog in the API.
 */

import { apiFetch } from "@/lib/api/client"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

export function normalizeReviewTasksList(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord) as Record<string, unknown>[]
  if (isRecord(data)) {
    if (Array.isArray(data.review_tasks)) return data.review_tasks.filter(isRecord) as Record<string, unknown>[]
    if (Array.isArray(data.tasks)) return data.tasks.filter(isRecord) as Record<string, unknown>[]
    if (Array.isArray(data.items)) return data.items.filter(isRecord) as Record<string, unknown>[]
    if (Array.isArray(data.results)) return data.results.filter(isRecord) as Record<string, unknown>[]
  }
  return []
}

export async function fetchSessionReviewTasks(sessionId: string): Promise<Record<string, unknown>[]> {
  const sid = sessionId.trim()
  if (!sid) return []
  const data = await apiFetch<unknown>(
    `/spectracheck/sessions/${encodeURIComponent(sid)}/review-tasks`,
    { method: "GET" },
  )
  return normalizeReviewTasksList(data)
}

export async function patchSessionReviewTask(
  sessionId: string,
  taskId: number | string,
  body: Record<string, unknown>,
): Promise<void> {
  const sid = sessionId.trim()
  if (!sid) throw new Error("Session id required.")
  await apiFetch(
    `/spectracheck/sessions/${encodeURIComponent(sid)}/review-tasks/${encodeURIComponent(String(taskId))}`,
    {
      method: "PATCH",
      body,
    },
  )
}

export type TaskStatusGroup = "open" | "in_progress" | "resolved" | "dismissed"

const STATUS_SET = new Set<TaskStatusGroup>(["open", "in_progress", "resolved", "dismissed"])

export function normalizeTaskStatus(row: Record<string, unknown>): TaskStatusGroup {
  const s = String(row.status ?? "").trim().toLowerCase()
  if (STATUS_SET.has(s as TaskStatusGroup)) return s as TaskStatusGroup
  return "open"
}

export function linkedRefsFromTaskMetadata(row: Record<string, unknown>): {
  evidenceId: string | null
  reportId: string | null
} {
  const m = row.metadata_json
  if (!isRecord(m)) return { evidenceId: null, reportId: null }
  const e = m.evidence_id ?? m.evidenceId
  const r = m.report_id ?? m.reportId
  return {
    evidenceId: e != null && e !== "" ? String(e) : null,
    reportId: r != null && r !== "" ? String(r) : null,
  }
}
