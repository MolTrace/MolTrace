// Notes left on a filing or a campaign.
//
// `/comments` addresses a note by subject pair, the same way `/review-tasks` addresses a
// task; the 404-not-403 semantics and the refusal of spectroscopy sessions are shared and
// live in `./subject-collaboration`.
//
// Spectroscopy sessions keep their own comment surface because a note there can be
// anchored to a specific piece of evidence — a thing a filing has no equivalent of — so
// this is not simply the same feature pointed elsewhere.
//
// A comment is the one surface of the four that can be edited after the fact: `resolved`
// marks a note settled without deleting what was said.

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

export type SubjectCommentRecord = components["schemas"]["EvidenceCommentRecord"]
export type SubjectCommentCreate = components["schemas"]["SubjectCommentCreate"]
export type SubjectCommentUpdate = components["schemas"]["EvidenceCommentUpdate"]

export type CommentType = SubjectCommentCreate["comment_type"]

export const COMMENT_TYPES = [
  "note",
  "question",
  "concern",
  "contradiction",
  "approval_note",
] as const satisfies readonly CommentType[]

const COPY: SubjectSurfaceCopy = {
  collection: "Comments",
  sessionSurface:
    "Spectroscopy sessions have their own comments, where a note can also be pinned to a specific piece of evidence.",
}

export function normalizeSubjectComments(data: unknown): SubjectCommentRecord[] {
  return normalizeSubjectRows<SubjectCommentRecord>(data, ["comments", "items", "results"])
}

export async function listSubjectComments(
  subjectType: SubjectType,
  subjectId: number,
): Promise<SubjectCommentRecord[]> {
  assertGenericSubject(subjectType)
  const data = await apiFetch<unknown>(`/comments?${subjectQuery(subjectType, subjectId)}`, {
    method: "GET",
  })
  return normalizeSubjectComments(data)
}

export type LeaveSubjectCommentInput = {
  subjectType: SubjectType
  subjectId: number
  comment: string
  commentType?: CommentType
}

/** Build the create body. The model forbids unknown keys, so nothing optional is sent
 *  blank; `comment_type` carries a server-side default but is required by the generated
 *  type, so it is always sent. */
export function buildLeaveSubjectCommentBody(
  input: LeaveSubjectCommentInput,
): SubjectCommentCreate {
  return {
    subject_type: input.subjectType,
    subject_id: input.subjectId,
    comment: input.comment.trim(),
    comment_type: input.commentType ?? "note",
  }
}

export async function leaveSubjectComment(
  input: LeaveSubjectCommentInput,
): Promise<SubjectCommentRecord> {
  assertGenericSubject(input.subjectType)
  return apiFetch<SubjectCommentRecord>("/comments", {
    method: "POST",
    body: buildLeaveSubjectCommentBody(input),
  })
}

export async function updateSubjectComment(
  commentId: number,
  patch: SubjectCommentUpdate,
): Promise<SubjectCommentRecord> {
  return apiFetch<SubjectCommentRecord>(`/comments/${encodeURIComponent(String(commentId))}`, {
    method: "PATCH",
    body: patch,
  })
}

export function describeSubjectCommentError(
  err: unknown,
  subjectType: SubjectType,
): SubjectCollaborationError {
  return describeSubjectCollaborationError(err, subjectType, COPY)
}

/** Unsettled notes first, then newest — what a reader still has to deal with, on top. */
export function sortSubjectComments(comments: SubjectCommentRecord[]): SubjectCommentRecord[] {
  return [...comments].sort((a, b) => {
    if (Boolean(a.resolved) !== Boolean(b.resolved)) return a.resolved ? 1 : -1
    const whenA = String(a.created_at ?? "")
    const whenB = String(b.created_at ?? "")
    if (whenA !== whenB) return whenA < whenB ? 1 : -1
    return Number(b.id ?? 0) - Number(a.id ?? 0)
  })
}

export function unresolvedCommentCount(comments: SubjectCommentRecord[]): number {
  return comments.filter((c) => !c.resolved).length
}
