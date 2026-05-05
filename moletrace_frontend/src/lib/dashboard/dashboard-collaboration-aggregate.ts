/**
 * Dashboard collaboration rollup from per-session SpectraCheck endpoints (no global index).
 */

import { fetchSessionReportsList } from "@/src/lib/spectracheck/spectracheck-backend-session"
import { fetchSessionComments } from "@/src/lib/spectracheck/spectracheck-session-comments"
import { fetchSessionReviewTasks } from "@/src/lib/spectracheck/review-queue"
import {
  normalizeReportsListPayload,
  reportFilterBucket,
  sessionRecordId,
} from "@/src/lib/reports/saved-reports"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function normEmail(e: string | null | undefined): string | null {
  if (!e?.trim()) return null
  return e.trim().toLowerCase()
}

function taskStatus(t: Record<string, unknown>): string {
  return String(t.status ?? "").trim().toLowerCase()
}

function isOpenReviewTask(t: Record<string, unknown>): boolean {
  const s = taskStatus(t)
  return s === "open" || s === "in_progress"
}

function isCommentUnresolved(c: Record<string, unknown>): boolean {
  return c.resolved !== true
}

export type DashboardCollaborationAggregate = {
  /** True when at least one session returned data from collaboration endpoints. */
  available: boolean
  /** Some session-level requests failed (counts may be partial). */
  partial: boolean
  openReviewTasks: number
  commentsUnresolved: number
  reportsPendingApproval: number
  releasedReports: number
  assignedToMe: number
}

const BATCH = 6

export async function fetchDashboardCollaborationAggregate(
  sessions: Record<string, unknown>[],
  viewerEmail: string | null,
): Promise<DashboardCollaborationAggregate> {
  const viewer = normEmail(viewerEmail)
  let openReviewTasks = 0
  let commentsUnresolved = 0
  let reportsPendingApproval = 0
  let releasedReports = 0
  let assignedToMe = 0
  let anySuccess = false
  let partial = false

  if (sessions.length === 0) {
    return {
      available: true,
      partial: false,
      openReviewTasks: 0,
      commentsUnresolved: 0,
      reportsPendingApproval: 0,
      releasedReports: 0,
      assignedToMe: 0,
    }
  }

  for (let i = 0; i < sessions.length; i += BATCH) {
    const chunk = sessions.slice(i, i + BATCH)
    const settled = await Promise.all(
      chunk.map(async (session) => {
        const sid = sessionRecordId(session)
        if (!sid) return { ok: false as const }
        const results = await Promise.allSettled([
          fetchSessionReviewTasks(sid),
          fetchSessionComments(sid),
          fetchSessionReportsList(sid),
        ])
        return { ok: true as const, sid, results }
      }),
    )

    for (const row of settled) {
      if (!row.ok) continue
      const [tr, cr, rr] = row.results
      let sessionTouched = false

      if (tr.status === "fulfilled") {
        sessionTouched = true
        for (const t of tr.value) {
          if (!isRecord(t)) continue
          if (isOpenReviewTask(t)) openReviewTasks += 1
          const asg = t.assigned_to ?? t.assignedTo
          if (
            viewer &&
            typeof asg === "string" &&
            normEmail(asg) === viewer &&
            isOpenReviewTask(t)
          ) {
            assignedToMe += 1
          }
        }
      } else {
        partial = true
      }

      if (cr.status === "fulfilled") {
        sessionTouched = true
        for (const c of cr.value) {
          if (!isRecord(c)) continue
          if (isCommentUnresolved(c)) commentsUnresolved += 1
        }
      } else {
        partial = true
      }

      if (rr.status === "fulfilled") {
        sessionTouched = true
        const list = normalizeReportsListPayload(rr.value)
        for (const rep of list) {
          if (!isRecord(rep)) continue
          const bucket = reportFilterBucket(rep)
          if (bucket === "approved") releasedReports += 1
          else if (bucket === "review_required" || bucket === "draft") reportsPendingApproval += 1
        }
      } else {
        partial = true
      }

      if (sessionTouched) anySuccess = true
    }
  }

  return {
    available: anySuccess,
    partial,
    openReviewTasks,
    commentsUnresolved,
    reportsPendingApproval,
    releasedReports,
    assignedToMe,
  }
}
