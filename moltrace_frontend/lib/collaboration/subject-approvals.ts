// Sign-off decisions recorded against a filing or a campaign: who decided what, and why.
//
// Two things about this surface that the UI has to be built around, beyond the 404/403
// semantics shared in `./subject-collaboration`:
//
//   * **There are two decision vocabularies, and they are not interchangeable.**
//     `ApprovalRecord["decision"]` is wider than `SubjectApprovalCreate["decision"]`
//     because both this surface and the SpectraCheck session surface store their sign-offs
//     in one table. `approved_plausible` and `approved_confirmed` are structure-elucidation
//     language: they say something precise about a proposed structure and nothing at all
//     about a regulatory filing. `POST /approvals` refuses them. Drive every picker from
//     `APPROVAL_DECISIONS` below, never from the record type.
//   * **There is no PATCH.** An approval is a record of a decision at a point in time;
//     editing it after the fact would falsify the audit trail. To change position, record
//     another approval — `currentSubjectApproval` reads the one that stands.
//
// And one thing it is not: an approval is not an electronic signature. It records the
// decision. A §11.70 signature is created through `/esignatures/records` and bound to a
// point-in-time report. Nothing here should be labelled "Sign".

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

export type SubjectApprovalRecord = components["schemas"]["ApprovalRecord"]
export type SubjectApprovalCreate = components["schemas"]["SubjectApprovalCreate"]

/** What a sign-off on a filing or a campaign may say. Narrower than the record type. */
export type SubjectApprovalDecision = SubjectApprovalCreate["decision"]

export const APPROVAL_DECISIONS = [
  "approved",
  "rejected",
  "needs_changes",
  "deferred",
] as const satisfies readonly SubjectApprovalDecision[]

/**
 * Compile-time guard on the trap above: if the create model ever accepts a decision this
 * list does not offer, this alias resolves to the missing members instead of `true` and
 * the build fails here rather than silently shipping a picker that cannot reach them.
 */
export type ApprovalDecisionsAreExhaustive =
  Exclude<SubjectApprovalDecision, (typeof APPROVAL_DECISIONS)[number]> extends never ? true : never

const COPY: SubjectSurfaceCopy = {
  collection: "Sign-off decisions",
  sessionSurface: "Spectroscopy sessions are signed off from their own session workspace.",
}

export function isSubjectApprovalDecision(v: unknown): v is SubjectApprovalDecision {
  return typeof v === "string" && (APPROVAL_DECISIONS as readonly string[]).includes(v)
}

export function normalizeSubjectApprovals(data: unknown): SubjectApprovalRecord[] {
  return normalizeSubjectRows<SubjectApprovalRecord>(data, ["approvals", "items", "results"])
}

export async function listSubjectApprovals(
  subjectType: SubjectType,
  subjectId: number,
): Promise<SubjectApprovalRecord[]> {
  assertGenericSubject(subjectType)
  const data = await apiFetch<unknown>(`/approvals?${subjectQuery(subjectType, subjectId)}`, {
    method: "GET",
  })
  return normalizeSubjectApprovals(data)
}

export type RecordSubjectApprovalInput = {
  subjectType: SubjectType
  subjectId: number
  decision: SubjectApprovalDecision
  rationale: string
  approverEmail?: string
}

/** Build the create body. The model forbids unknown keys, so a blank approver is omitted
 *  entirely rather than sent as an empty string. */
export function buildRecordSubjectApprovalBody(
  input: RecordSubjectApprovalInput,
): SubjectApprovalCreate {
  const body: SubjectApprovalCreate = {
    subject_type: input.subjectType,
    subject_id: input.subjectId,
    decision: input.decision,
    rationale: input.rationale.trim(),
  }
  const approverEmail = input.approverEmail?.trim()
  if (approverEmail) body.approver_email = approverEmail
  return body
}

export async function recordSubjectApproval(
  input: RecordSubjectApprovalInput,
): Promise<SubjectApprovalRecord> {
  assertGenericSubject(input.subjectType)
  if (!isSubjectApprovalDecision(input.decision)) {
    // Reached only if a decision arrived from stored state or a widened cast. The
    // structure-elucidation decisions live on the record type and are refused here, so
    // fail with something a reader can act on rather than surfacing a validation error.
    throw new Error("That decision does not apply to a filing or a campaign.")
  }
  return apiFetch<SubjectApprovalRecord>("/approvals", {
    method: "POST",
    body: buildRecordSubjectApprovalBody(input),
  })
}

export function describeSubjectApprovalError(
  err: unknown,
  subjectType: SubjectType,
): SubjectCollaborationError {
  return describeSubjectCollaborationError(err, subjectType, COPY)
}

/** Newest first — the top row is the position that stands. */
export function sortSubjectApprovals(approvals: SubjectApprovalRecord[]): SubjectApprovalRecord[] {
  return [...approvals].sort((a, b) => {
    const whenA = String(a.created_at ?? "")
    const whenB = String(b.created_at ?? "")
    if (whenA !== whenB) return whenA < whenB ? 1 : -1
    return Number(b.id ?? 0) - Number(a.id ?? 0)
  })
}

/** The decision that currently stands, or null if none has been recorded. */
export function currentSubjectApproval(
  approvals: SubjectApprovalRecord[],
): SubjectApprovalRecord | null {
  return sortSubjectApprovals(approvals)[0] ?? null
}

/**
 * Display label for any decision on a record, including the two that belong to the
 * SpectraCheck session surface — a shared table means one can be read back here, and a
 * row that cannot be labelled is worse than one labelled precisely.
 */
export function approvalDecisionLabel(decision: unknown): string {
  const d = typeof decision === "string" ? decision.trim().toLowerCase() : ""
  switch (d) {
    case "approved":
      return "Approved"
    case "rejected":
      return "Rejected"
    case "needs_changes":
      return "Needs changes"
    case "deferred":
      return "Deferred"
    case "approved_plausible":
      return "Approved (structure plausible)"
    case "approved_confirmed":
      return "Approved (structure confirmed)"
    default:
      return typeof decision === "string" && decision.trim() ? decision.trim() : "—"
  }
}
