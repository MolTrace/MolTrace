/**
 * Client for the FID run review routes.
 *
 * `653b402` opened `review` / `approve` / `reject` / `request-changes` from
 * admin-only to any authenticated user who is not the run's author. The rule the
 * admin gate was standing in for is segregation of duties — the reviewer in a lab
 * is a senior chemist, not IT — so the check is now "somebody else", not "an
 * administrator".
 *
 * Two limits of the current backend shape the surface built on this, and both are
 * read-side. They are recorded here because neither is visible from the route
 * list, and a reader who does not know them will read the result as a bug:
 *
 * 1. **Discovery is owner-scoped.** `GET /fid/runs` and `GET /fid/runs/{id}` run
 *    through `_user_scope_for_context`, which returns the caller's own id for
 *    anyone who is not an admin or a system key. A non-admin therefore lists only
 *    their own runs and gets a non-leaking 404 on anybody else's. So a non-admin
 *    peer cannot *find* a colleague's run to review, even though the POST would
 *    accept their verdict — `_submit_fid_run_review` never calls
 *    `_get_visible_fid_run`. Until the read scope is opened, the cross-user review
 *    queue is populated for admins only; for everyone else this surface is their
 *    own runs plus the decisions others have recorded on them.
 * 2. **The SpectraCheck raw-FID tab cannot anchor to a run.**
 *    `NMRRawFIDProcessResponse` (what `POST /nmr/raw-fid/process` returns) has no
 *    `fid_run_id` and is `extra="forbid"`. Only `FIDPreviewReport`, returned by the
 *    vault route `POST /raw-fid/{archive_id}/process`, carries one. That is why
 *    this surface is driven by the run *list* rather than hung off the process
 *    response — the list is the only place the ids exist today.
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
