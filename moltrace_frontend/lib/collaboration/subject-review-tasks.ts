// Review tasks addressed to a filing or a campaign — the first slice of the
// collaboration layer that is not SpectraCheck-only.
//
// A review task used to require a spectroscopy session, so a regulatory team could
// not say "someone look at this filing" and a process team could not say "someone
// check this campaign". `/review-tasks` addresses a task by a subject pair
// (`subject_type` + `subject_id`) instead, and a record now carries `module` so a
// mixed queue reads without re-deriving where each task came from.
//
// The 404-not-403 semantics and the refusal of spectroscopy sessions are shared with
// the other three subject surfaces and live in `./subject-collaboration`.

import { apiFetch } from "@/lib/api/client"
import type { components } from "@/src/lib/api/schema"
import {
  assertGenericSubject,
  describeSubjectCollaborationError,
  normalizeSubjectRows,
  subjectKindLabel,
  subjectQuery,
  type SubjectCollaborationError,
  type SubjectCollaborationErrorKind,
  type SubjectSurfaceCopy,
  type SubjectType,
} from "@/lib/collaboration/subject-collaboration"

export { subjectKindLabel, type SubjectType }

export type ReviewTaskRecord = components["schemas"]["ReviewTaskRecord"]
export type SubjectReviewTaskCreate = components["schemas"]["SubjectReviewTaskCreate"]
export type ReviewTaskUpdate = components["schemas"]["ReviewTaskUpdate"]

export type ReviewTaskStatus = SubjectReviewTaskCreate["status"]
export type ReviewTaskPriority = SubjectReviewTaskCreate["priority"]

export const REVIEW_TASK_STATUSES = ["open", "in_progress", "resolved", "dismissed"] as const
export const REVIEW_TASK_PRIORITIES = ["low", "medium", "high", "critical"] as const

const COPY: SubjectSurfaceCopy = {
  collection: "Review tasks",
  sessionSurface: "Spectroscopy sessions are reviewed from their own session workspace.",
}

/** Statuses that mean the task no longer needs work. */
const CLOSED_STATUSES = new Set<string>(["resolved", "dismissed"])

export function isReviewTaskClosed(task: ReviewTaskRecord): boolean {
  return CLOSED_STATUSES.has(String(task.status))
}

/** The endpoint returns a bare array; tolerate a wrapped list rather than blanking
 *  the panel if the shape is ever widened. */
export function normalizeReviewTasks(data: unknown): ReviewTaskRecord[] {
  return normalizeSubjectRows<ReviewTaskRecord>(data, ["review_tasks", "tasks", "items", "results"])
}

export async function listSubjectReviewTasks(
  subjectType: SubjectType,
  subjectId: number,
): Promise<ReviewTaskRecord[]> {
  assertGenericSubject(subjectType)
  const data = await apiFetch<unknown>(`/review-tasks?${subjectQuery(subjectType, subjectId)}`, {
    method: "GET",
  })
  return normalizeReviewTasks(data)
}

export type RaiseReviewTaskInput = {
  subjectType: SubjectType
  subjectId: number
  title: string
  description?: string
  assignedTo?: string
  priority?: ReviewTaskPriority
}

/** Build the create body. The model forbids unknown keys, so optional fields are
 *  omitted entirely rather than sent as empty strings. `status` and `priority` carry
 *  server-side defaults but are required by the generated type, so they are always sent. */
export function buildRaiseReviewTaskBody(input: RaiseReviewTaskInput): SubjectReviewTaskCreate {
  const body: SubjectReviewTaskCreate = {
    subject_type: input.subjectType,
    subject_id: input.subjectId,
    title: input.title.trim(),
    status: "open",
    priority: input.priority ?? "medium",
  }
  const description = input.description?.trim()
  if (description) body.description = description
  const assignedTo = input.assignedTo?.trim()
  if (assignedTo) body.assigned_to = assignedTo
  return body
}

export async function raiseSubjectReviewTask(
  input: RaiseReviewTaskInput,
): Promise<ReviewTaskRecord> {
  assertGenericSubject(input.subjectType)
  return apiFetch<ReviewTaskRecord>("/review-tasks", {
    method: "POST",
    body: buildRaiseReviewTaskBody(input),
  })
}

export async function updateSubjectReviewTask(
  taskId: number,
  patch: ReviewTaskUpdate,
): Promise<ReviewTaskRecord> {
  return apiFetch<ReviewTaskRecord>(`/review-tasks/${encodeURIComponent(String(taskId))}`, {
    method: "PATCH",
    body: patch,
  })
}

// ── error shapes ─────────────────────────────────────────────────────────────
export type SubjectReviewTaskErrorKind = SubjectCollaborationErrorKind
export type SubjectReviewTaskError = SubjectCollaborationError

export function describeSubjectReviewTaskError(
  err: unknown,
  subjectType: SubjectType,
): SubjectReviewTaskError {
  return describeSubjectCollaborationError(err, subjectType, COPY)
}

/** Open tasks first, then most recently updated — the order a reviewer wants. */
export function sortReviewTasks(tasks: ReviewTaskRecord[]): ReviewTaskRecord[] {
  return [...tasks].sort((a, b) => {
    const closedA = isReviewTaskClosed(a)
    const closedB = isReviewTaskClosed(b)
    if (closedA !== closedB) return closedA ? 1 : -1
    const whenA = String(a.updated_at ?? "")
    const whenB = String(b.updated_at ?? "")
    if (whenA !== whenB) return whenA < whenB ? 1 : -1
    return Number(b.id ?? 0) - Number(a.id ?? 0)
  })
}

export function openReviewTaskCount(tasks: ReviewTaskRecord[]): number {
  return tasks.filter((t) => !isReviewTaskClosed(t)).length
}
