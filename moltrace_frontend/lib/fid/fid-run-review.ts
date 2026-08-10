/**
 * Client for the FID run review routes.
 *
 * `653b402` opened `review` / `approve` / `reject` / `request-changes` from
 * admin-only to any authenticated user who is not the run's author. The rule the
 * admin gate was standing in for is segregation of duties — the reviewer in a lab
 * is a senior chemist, not IT — so the check is now "somebody else", not "an
 * administrator".
 *
 * Both read-side limits recorded here previously are now closed backend-side. What
 * replaced them is a scoped rule, not an open door, and the shape of it is what a
 * reader of this surface needs to know:
 *
 * 1. **Discovery is team-scoped, and only while a review is owed.** `GET /fid/runs`
 *    returns a run when you wrote it, when it is an *open* item (`pending_review` or
 *    `needs_revision`) produced by somebody who shares an active organization with
 *    you, or when you have already recorded a decision on it. So the queue fills
 *    with colleagues' runs awaiting a verdict, a colleague's *approved* run drops
 *    back out of view, and a run you signed stays reachable to you forever. An
 *    empty queue for a user on no team is correct, not a fault — there are no
 *    colleagues to review for, and the panel should say so rather than look broken.
 *    The write routes enforce the same rule: a run you cannot open 404s on POST too.
 * 2. **The process response now names its run.** `NMRRawFIDProcessResponse` carries
 *    `fid_run_id`, so the Raw FID tab can anchor review to the run the user just
 *    created instead of finding it again in the list. The list remains the entry
 *    point for the *queue* — reviewing a colleague's work starts from the list, by
 *    definition, since you did not process it.
 *
 * Two per-request fields on `FIDRunRecord` carry the caller's relationship to a run,
 * because the list is now mixed: `viewer_is_author` separates "mine" from "awaiting
 * me", and `viewer_can_review` is false for the author, so the segregation-of-duties
 * refusal can be shown before the POST rather than read back out of a 409.
 */

import { ApiError, apiFetch } from "@/lib/api/client"
import type { components } from "@/src/lib/api/schema"

export type FIDRunRecord = components["schemas"]["FIDRunRecord"]
export type FIDRunReviewDecision = components["schemas"]["FIDRunReviewDecisionRecord"]
export type FIDRunReviewCreate = components["schemas"]["FIDRunReviewCreate"]
export type FIDReviewStatus = FIDRunRecord["review_status"]

/** The four decisions a reviewer can record, in the order they are offered. */
export const FID_REVIEW_ACTIONS = ["approve", "request_changes", "reject", "review"] as const
export type FIDReviewAction = (typeof FID_REVIEW_ACTIONS)[number]

/** Path segment per action — `request_changes` is the one that is not its own name. */
const ACTION_PATHS: Record<FIDReviewAction, string> = {
  approve: "approve",
  request_changes: "request-changes",
  reject: "reject",
  review: "review",
}

/** Reader-facing labels. The stored action values are never renamed. */
export const FID_REVIEW_ACTION_LABELS: Record<FIDReviewAction, string> = {
  approve: "Approve",
  request_changes: "Request changes",
  reject: "Reject",
  review: "Add comment",
}

export const FID_REVIEW_STATUS_LABELS: Record<string, string> = {
  pending_review: "Awaiting review",
  approved: "Approved",
  rejected: "Rejected",
  needs_revision: "Changes requested",
}

export function fidReviewStatusLabel(status: string): string {
  return FID_REVIEW_STATUS_LABELS[status] ?? status.replace(/_/g, " ")
}

export async function fetchFidRuns(limit = 20): Promise<FIDRunRecord[]> {
  return apiFetch<FIDRunRecord[]>(`/fid/runs?limit=${encodeURIComponent(String(limit))}`, {
    method: "GET",
  })
}

export async function fetchFidRunReviewDecisions(runId: number): Promise<FIDRunReviewDecision[]> {
  return apiFetch<FIDRunReviewDecision[]>(
    `/fid/runs/${encodeURIComponent(String(runId))}/review-decisions`,
    { method: "GET" },
  )
}

export async function submitFidRunReview(
  runId: number,
  action: FIDReviewAction,
  comment: string | null,
): Promise<FIDRunReviewDecision> {
  const body: FIDRunReviewCreate = { action, comment: comment?.trim() ? comment.trim() : null }
  return apiFetch<FIDRunReviewDecision>(
    `/fid/runs/${encodeURIComponent(String(runId))}/${ACTION_PATHS[action]}`,
    { method: "POST", body },
  )
}

/**
 * The backend's own sentence when a reviewer is the run's author, or null.
 *
 * Deliberately 409 on the backend and not 403: the caller *is* entitled to review
 * runs, just not this one. A 403 would additionally be replaced wholesale by the
 * `/api/backend` proxy's 401/403 sanitiser, so the explanation would never reach
 * the screen and the feature would read as broken. Because that distinction is
 * carried by the status code, branch on the status — never on the prose.
 *
 * Reads `data.detail` before `message`: `message` has already been through
 * `sanitizePublicApiErrorMessage`, which passes a 409 through today but is not
 * contracted to.
 */
export function selfReviewMessage(err: unknown): string | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null
  const detail =
    err.data && typeof err.data === "object"
      ? (err.data as { detail?: unknown }).detail
      : undefined
  if (typeof detail === "string" && detail.trim()) return detail.trim()
  return err.message || "This run needs a review from someone other than its author."
}
