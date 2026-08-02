// Review tasks addressed to a filing or a campaign — the first slice of the
// collaboration layer that is not SpectraCheck-only.
//
// A review task used to require a spectroscopy session, so a regulatory team could
// not say "someone look at this filing" and a process team could not say "someone
// check this campaign". `/review-tasks` addresses a task by a subject pair
// (`subject_type` + `subject_id`) instead, and a record now carries `module` so a
// mixed queue reads without re-deriving where each task came from.
//
// Two behaviours the endpoint has that the UI has to be built around:
//
//   * A subject the caller cannot reach answers **404**, exactly as a subject that
//     does not exist does. That is deliberate — raising a task must not be usable to
//     probe whether another customer's filing exists — so it is a not-found, never an
//     "insufficient permissions". `describeSubjectReviewTaskError` keeps those apart.
//   * SpectraCheck sessions are **refused** here. They keep the richer session-scoped
//     surface with per-session reviewer roles; see
//     `src/lib/spectracheck/review-queue.ts`. `SubjectType` below excludes them so the
//     wrong call does not compile, and `assertGenericSubject` catches a dynamic one.

import { ApiError, apiFetch } from "@/lib/api/client"
import type { components } from "@/src/lib/api/schema"

export type ReviewTaskRecord = components["schemas"]["ReviewTaskRecord"]
export type SubjectReviewTaskCreate = components["schemas"]["SubjectReviewTaskCreate"]
export type ReviewTaskUpdate = components["schemas"]["ReviewTaskUpdate"]

export type ReviewTaskStatus = SubjectReviewTaskCreate["status"]
export type ReviewTaskPriority = SubjectReviewTaskCreate["priority"]

/** The subject types this endpoint serves. Spectroscopy sessions are handled by
 *  their own session-scoped surface and are excluded on purpose. */
export type SubjectType = Exclude<
  SubjectReviewTaskCreate["subject_type"],
  "spectracheck_session"
>

export const REVIEW_TASK_STATUSES = ["open", "in_progress", "resolved", "dismissed"] as const
export const REVIEW_TASK_PRIORITIES = ["low", "medium", "high", "critical"] as const

/** Statuses that mean the task no longer needs work. */
const CLOSED_STATUSES = new Set<string>(["resolved", "dismissed"])

export function isReviewTaskClosed(task: ReviewTaskRecord): boolean {
  return CLOSED_STATUSES.has(String(task.status))
}

/** Plain-language name for the product a task belongs to. */
export function subjectKindLabel(subjectType: SubjectType): string {
  return subjectType === "regulatory_dossier" ? "filing" : "campaign"
}

function assertGenericSubject(subjectType: SubjectType): void {
  // Defensive: the type excludes it, but a value read from a route param or stored
  // state is only as narrow as its cast. Fail here rather than send a request the
  // server will refuse.
  if (String(subjectType) === "spectracheck_session") {
    throw new Error("Spectroscopy sessions use their own review surface.")
  }
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return v != null && typeof v === "object" && !Array.isArray(v)
}

/** The endpoint returns a bare array; tolerate a wrapped list rather than blanking
 *  the panel if the shape is ever widened. */
export function normalizeReviewTasks(data: unknown): ReviewTaskRecord[] {
  const rows = Array.isArray(data)
    ? data
    : isRecord(data)
      ? ((["review_tasks", "tasks", "items", "results"]
          .map((k) => data[k])
          .find(Array.isArray) as unknown[] | undefined) ?? [])
      : []
  return rows.filter(isRecord) as ReviewTaskRecord[]
}

export async function listSubjectReviewTasks(
  subjectType: SubjectType,
  subjectId: number,
): Promise<ReviewTaskRecord[]> {
  assertGenericSubject(subjectType)
  const query = new URLSearchParams({
    subject_type: subjectType,
    subject_id: String(subjectId),
  })
  const data = await apiFetch<unknown>(`/review-tasks?${query.toString()}`, { method: "GET" })
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
export type SubjectReviewTaskErrorKind = "not_found" | "wrong_surface" | "other"

export type SubjectReviewTaskError = {
  kind: SubjectReviewTaskErrorKind
  message: string
}

/**
 * Classify a failure so the caller can render the right state.
 *
 * `not_found` covers both "this does not exist" and "this is not yours" — the server
 * refuses to say which, and the UI must not guess. Rendering it as a permissions
 * error would put a claim on screen the response does not support.
 */
export function describeSubjectReviewTaskError(
  err: unknown,
  subjectType: SubjectType,
): SubjectReviewTaskError {
  const kind = subjectKindLabel(subjectType)
  if (err instanceof ApiError) {
    if (err.status === 404) {
      return {
        kind: "not_found",
        message: `This ${kind} is no longer available. It may have been removed, or it may belong to another organization.`,
      }
    }
    if (err.status === 403) {
      return {
        kind: "wrong_surface",
        message: "Spectroscopy sessions are reviewed from their own session workspace.",
      }
    }
  }
  const message = err instanceof Error && err.message.trim() ? err.message.trim() : ""
  return { kind: "other", message: message || "Review tasks could not be loaded. Please try again." }
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
