// Reviewer nominations on a filing or a campaign: who is expected to look at it.
//
// **A nomination does not grant access.** Access comes from the owning team. Nominating
// someone outside the team succeeds and lets them in nowhere — that is deliberate, because
// an assignment that silently widened access would be a second, weaker way into a record.
//
// That has a direct consequence for every string this module feeds: it is "request review
// from" and "nominate a reviewer", never "share with", "give access to" or "invite". If a
// nominated person cannot open the record, that is correct behaviour, not a failure to
// retry. `NOMINATION_DOES_NOT_GRANT_ACCESS` is the sentence the UI says out loud.
//
// Note the asymmetry with SpectraCheck: on a *session*, a reviewer row does confer a
// session role. The two surfaces genuinely differ in meaning, so the session copy is not a
// model for this one.
//
// **There is no PATCH.** Re-posting the same `reviewer_email` for the same subject updates
// the existing row in place rather than stacking duplicates, so changing a status is
// another POST.

import { apiFetch } from "@/lib/api/client"
import type { components } from "@/src/lib/api/schema"
import {
  assertGenericSubject,
  describeSubjectCollaborationError,
  normalizeSubjectRows,
  subjectQuery,
  type SubjectCollaborationError,
  type SubjectSurfaceCopy,
  type SubjectType,
} from "@/lib/collaboration/subject-collaboration"

export type SubjectReviewerRecord = components["schemas"]["SessionReviewerRecord"]
export type SubjectReviewerCreate = components["schemas"]["SubjectReviewerCreate"]

export type ReviewerStatus = SubjectReviewerCreate["status"]

export const REVIEWER_STATUSES = [
  "assigned",
  "in_review",
  "completed",
  "removed",
] as const satisfies readonly ReviewerStatus[]

/** Statuses that mean the nomination is no longer live. */
const CLOSED_REVIEWER_STATUSES = new Set<string>(["completed", "removed"])

/** Said out loud in the UI, so nobody reads a nomination as a grant. */
export const NOMINATION_DOES_NOT_GRANT_ACCESS =
  "Nominating someone records that they are expected to look. It does not give them access — that comes from the team that owns this record — so someone outside the team will not be able to open it."

const COPY: SubjectSurfaceCopy = {
  collection: "Reviewer nominations",
  sessionSurface:
    "Spectroscopy sessions assign reviewers from their own session workspace, where a reviewer also takes on a role for that session.",
}

export function normalizeSubjectReviewers(data: unknown): SubjectReviewerRecord[] {
  return normalizeSubjectRows<SubjectReviewerRecord>(data, ["reviewers", "items", "results"])
}

export async function listSubjectReviewers(
  subjectType: SubjectType,
  subjectId: number,
): Promise<SubjectReviewerRecord[]> {
  assertGenericSubject(subjectType)
  const data = await apiFetch<unknown>(`/reviewers?${subjectQuery(subjectType, subjectId)}`, {
    method: "GET",
  })
  return normalizeSubjectReviewers(data)
}

export type NominateSubjectReviewerInput = {
  subjectType: SubjectType
  subjectId: number
  reviewerEmail: string
  status?: ReviewerStatus
}

/** Build the create body. `status` carries a server-side default but is required by the
 *  generated type, so it is always sent. */
export function buildNominateSubjectReviewerBody(
  input: NominateSubjectReviewerInput,
): SubjectReviewerCreate {
  return {
    subject_type: input.subjectType,
    subject_id: input.subjectId,
    reviewer_email: input.reviewerEmail.trim(),
    status: input.status ?? "assigned",
  }
}

export async function nominateSubjectReviewer(
  input: NominateSubjectReviewerInput,
): Promise<SubjectReviewerRecord> {
  assertGenericSubject(input.subjectType)
  return apiFetch<SubjectReviewerRecord>("/reviewers", {
    method: "POST",
    body: buildNominateSubjectReviewerBody(input),
  })
}

/** Change a nomination's status. There is no PATCH — re-posting the same reviewer updates
 *  the existing row in place, so this is the same call with a different status. */
export async function setSubjectReviewerStatus(
  subjectType: SubjectType,
  subjectId: number,
  reviewerEmail: string,
  status: ReviewerStatus,
): Promise<SubjectReviewerRecord> {
  return nominateSubjectReviewer({ subjectType, subjectId, reviewerEmail, status })
}

export function describeSubjectReviewerError(
  err: unknown,
  subjectType: SubjectType,
): SubjectCollaborationError {
  return describeSubjectCollaborationError(err, subjectType, COPY)
}

export function isReviewerNominationClosed(reviewer: SubjectReviewerRecord): boolean {
  return CLOSED_REVIEWER_STATUSES.has(String(reviewer.status))
}

/** Live nominations first, then most recently updated. */
export function sortSubjectReviewers(
  reviewers: SubjectReviewerRecord[],
): SubjectReviewerRecord[] {
  return [...reviewers].sort((a, b) => {
    const closedA = isReviewerNominationClosed(a)
    const closedB = isReviewerNominationClosed(b)
    if (closedA !== closedB) return closedA ? 1 : -1
    const whenA = String(a.updated_at ?? "")
    const whenB = String(b.updated_at ?? "")
    if (whenA !== whenB) return whenA < whenB ? 1 : -1
    return Number(b.id ?? 0) - Number(a.id ?? 0)
  })
}

/** Nominations still expected to produce a look. */
export function pendingReviewerCount(reviewers: SubjectReviewerRecord[]): number {
  return reviewers.filter((r) => !isReviewerNominationClosed(r)).length
}
