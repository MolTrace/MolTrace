// Shared core for the collaboration surfaces that address a filing or a campaign by a
// subject pair (`subject_type` + `subject_id`) rather than by spectroscopy session:
// review tasks, comments, sign-off decisions and reviewer nominations.
//
// Four behaviours every one of them shares, and which the UI has to be built around:
//
//   * A subject the caller cannot reach answers **404**, exactly as one that does not
//     exist does. That is deliberate — addressing a record must not be usable to probe
//     whether another organization's filing exists — so it is a not-found, never an
//     "insufficient permissions". `describeSubjectCollaborationError` keeps those apart.
//   * SpectraCheck sessions are **refused** on all four. They keep their own richer
//     session-scoped surfaces — per-session reviewer roles, notes anchored to a specific
//     piece of evidence — see `src/lib/spectracheck/review-queue.ts`. `SubjectType`
//     excludes them so the wrong call does not compile, and `assertGenericSubject`
//     catches one that arrived dynamically.
//   * The create models are `extra="forbid"`, so an optional field is omitted entirely
//     rather than sent as an empty string.
//   * A record carries `module`, so a mixed queue reads without re-deriving where each
//     row came from.

import { ApiError } from "@/lib/api/client"
import type { components } from "@/src/lib/api/schema"

/**
 * The subject types the generic collaboration endpoints serve.
 *
 * Intersecting all four create models means a vocabulary that widens on only one of them
 * cannot silently widen this one — a subject type is only usable here once every surface
 * accepts it.
 */
export type SubjectType = Exclude<
  components["schemas"]["SubjectReviewTaskCreate"]["subject_type"] &
    components["schemas"]["SubjectCommentCreate"]["subject_type"] &
    components["schemas"]["SubjectApprovalCreate"]["subject_type"] &
    components["schemas"]["SubjectReviewerCreate"]["subject_type"],
  "spectracheck_session"
>

/**
 * What every collaboration surface takes when it is hosted inside the tabbed section.
 *
 * Each surface loads its own rows, so a tab that is never opened costs nothing. The count
 * callback exists so the host can badge a tab without a second request; a tab with no
 * badge has simply not been opened yet, and does not claim the surface is empty.
 */
export type SubjectSurfaceBodyProps = {
  subjectType: SubjectType
  /** Null while the route param is still resolving, or when it is not a number. */
  subjectId: number | null
  /** How many rows still need someone. */
  onAttentionCountChange?: (count: number) => void
}

/** Plain-language name for the thing a record hangs off. */
export function subjectKindLabel(subjectType: SubjectType): string {
  return subjectType === "regulatory_dossier" ? "filing" : "campaign"
}

export function assertGenericSubject(subjectType: SubjectType): void {
  // Defensive: the type excludes it, but a value read from a route param or stored state
  // is only as narrow as its cast. Fail here rather than send a request the server will
  // refuse.
  if (String(subjectType) === "spectracheck_session") {
    throw new Error("Spectroscopy sessions use their own review surface.")
  }
}

export function isRecord(v: unknown): v is Record<string, unknown> {
  return v != null && typeof v === "object" && !Array.isArray(v)
}

/** The query every one of these list endpoints takes. */
export function subjectQuery(subjectType: SubjectType, subjectId: number): string {
  return new URLSearchParams({
    subject_type: subjectType,
    subject_id: String(subjectId),
  }).toString()
}

/** These endpoints return a bare array; tolerate a wrapped list rather than blanking the
 *  panel if the shape is ever widened. */
export function normalizeSubjectRows<T>(data: unknown, wrapperKeys: readonly string[]): T[] {
  const rows = Array.isArray(data)
    ? data
    : isRecord(data)
      ? ((wrapperKeys.map((k) => data[k]).find(Array.isArray) as unknown[] | undefined) ?? [])
      : []
  return rows.filter(isRecord) as T[]
}

// ── error shapes ─────────────────────────────────────────────────────────────
export type SubjectCollaborationErrorKind = "not_found" | "wrong_surface" | "other"

export type SubjectCollaborationError = {
  kind: SubjectCollaborationErrorKind
  message: string
}

export type SubjectSurfaceCopy = {
  /** Sentence-initial plural noun for the collection: "Review tasks", "Comments". */
  collection: string
  /** What a spectroscopy session keeps instead, for the refused-surface branch. */
  sessionSurface: string
}

/**
 * Classify a failure so the caller can render the right state.
 *
 * `not_found` covers both "this does not exist" and "this is not yours" — the server
 * refuses to say which, and the UI must not guess. Rendering it as a permissions error
 * would put a claim on screen the response does not support.
 */
export function describeSubjectCollaborationError(
  err: unknown,
  subjectType: SubjectType,
  copy: SubjectSurfaceCopy,
): SubjectCollaborationError {
  const kind = subjectKindLabel(subjectType)
  if (err instanceof ApiError) {
    if (err.status === 404) {
      return {
        kind: "not_found",
        message: `This ${kind} is no longer available. It may have been removed, or it may belong to another organization.`,
      }
    }
    if (err.status === 403) {
      return { kind: "wrong_surface", message: copy.sessionSurface }
    }
  }
  const message = err instanceof Error && err.message.trim() ? err.message.trim() : ""
  return {
    kind: "other",
    message: message || `${copy.collection} could not be loaded. Please try again.`,
  }
}
