// Knowledge corpus governance — what a fact was justified by, and whether
// anyone still stands behind it.
//
// Three distinctions this module exists to keep apart. Each one is a state the
// UI could collapse into a neighbouring one and thereby assert something it
// does not know:
//
//  1. REVIEWED-AND-ACCEPTED vs NOBODY-HAS-LOOKED. `review_status` is
//     "accepted" | "rejected" | null, and `null` means unreviewed. Rendering
//     null as anything confident-sounding claims a review that never happened.
//     It is also not the same as "—": an em dash reads as "not applicable".
//
//  2. HAS-NO-REVIEW-STATE vs UNREVIEWED. Citations carry no `review_status`
//     field at all, so search does not filter them and there is nothing behind
//     a review marker on one. They get no review state — not "unreviewed".
//
//  3. STALE vs UNKNOWN provenance. A record whose `source_revision_id` differs
//     from its source's `current_revision_id` was justified by something the
//     source no longer says. A record whose `source_revision_id` is null
//     predates revisions entirely — unknown, never "up to date". The backend
//     deliberately did not backfill these, because claiming those records came
//     from what the source says now would be asserting something unknowable.

import { apiFetch } from "@/lib/api/client"
import { humanizeField } from "@/lib/ui/status"
import type { components } from "@/src/lib/api/schema"

export type KnowledgeSourceRevision = components["schemas"]["KnowledgeSourceRevision"]
export type KnowledgeSource = components["schemas"]["KnowledgeSource"]

// ── 1 · review state ──────────────────────────────────────────────────────────

/** `null` is a first-class state here, not an absence. */
export type ReviewState = "accepted" | "rejected" | "unreviewed"

export type ReviewStatePresentation = {
  label: string
  /** Longer form for a tooltip or detail row. */
  description: string
  /** Rejected must be visually distinct, not merely sorted lower. */
  tone: "accepted" | "rejected" | "unreviewed"
}

export const REVIEW_STATE_PRESENTATION: Record<ReviewState, ReviewStatePresentation> = {
  accepted: {
    label: "Accepted",
    description: "A reviewer looked at this and accepted it.",
    tone: "accepted",
  },
  rejected: {
    label: "Rejected",
    description: "A reviewer looked at this and refused it. It is shown because you asked to include refused material.",
    tone: "rejected",
  },
  unreviewed: {
    // Deliberately not a third confident-sounding label. "Pending", "Provisional"
    // and the like all imply a process is underway; nobody may ever look at this.
    label: "Not yet reviewed",
    description: "Nobody has reviewed this yet. That is not the same as having been accepted.",
    tone: "unreviewed",
  },
}

/** Read a record's review state. Anything that is not a recognised decision is
 *  unreviewed — an unknown string is not evidence that someone approved it. */
export function readReviewState(value: unknown): ReviewState {
  const raw = typeof value === "string" ? value.trim().toLowerCase() : ""
  if (raw === "accepted") return "accepted"
  if (raw === "rejected") return "rejected"
  return "unreviewed"
}

/**
 * Whether this record type has a review state at all.
 *
 * Citations do not: there is no `review_status` on `ExtractedCitation`, which is
 * also why search cannot filter them. Rendering "Not yet reviewed" on a citation
 * would invent a review process that does not exist for it.
 */
export function hasReviewState(recordType: string | null | undefined): boolean {
  return (recordType ?? "").trim().toLowerCase() !== "citation"
}

/** Label for the opt-in control. Says what it does, rather than "Show all". */
export const INCLUDE_REJECTED_LABEL = "Include material a reviewer refused"
export const INCLUDE_REJECTED_HINT =
  "Off by default. A refused record looks exactly like an accepted one otherwise, so refused results are marked when shown."
/** Citations are unfiltered either way, so the control must not imply otherwise. */
export const CITATIONS_UNFILTERED_NOTE =
  "Citations carry no review decision, so this setting does not affect them."

// ── 2 · source revisions ──────────────────────────────────────────────────────

/** `GET /knowledge/sources/{id}/revisions` — newest first. */
export async function fetchSourceRevisions(sourceId: number): Promise<KnowledgeSourceRevision[]> {
  return apiFetch<KnowledgeSourceRevision[]>(
    `/knowledge/sources/${encodeURIComponent(String(sourceId))}/revisions`,
  )
}

/**
 * Reader-facing names for the wire keys in `changed_fields`.
 *
 * Display only — the keys sent back on a PATCH are never renamed. `humanizeField`
 * handles the rest; these are the ones whose generic humanization reads wrong.
 */
const CHANGED_FIELD_LABELS: Record<string, string> = {
  doi: "DOI",
  source_url: "source link",
  patent_number: "patent number",
  reliability_label: "reliability label",
  publication_date: "publication date",
  source_type: "source type",
  jurisdiction_id: "jurisdiction",
}

export function changedFieldLabel(field: string): string {
  const key = field.trim().toLowerCase()
  return CHANGED_FIELD_LABELS[key] ?? humanizeField(field).toLowerCase()
}

/** "reliability label and publication date", for a sentence. */
export function changedFieldsSentence(fields: string[] | null | undefined): string {
  const labels = (fields ?? []).map(changedFieldLabel).filter(Boolean)
  if (labels.length === 0) return ""
  if (labels.length === 1) return labels[0]
  return `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`
}

// ── 3 · staleness ─────────────────────────────────────────────────────────────

/** `current` and `unknown` are different answers and are never merged. */
export type ProvenanceState = "current" | "superseded" | "unknown"

export type ProvenancePresentation = { label: string; description: string }

export const PROVENANCE_PRESENTATION: Record<ProvenanceState, ProvenancePresentation> = {
  current: {
    label: "Source unchanged",
    description: "This was extracted from what the source says now.",
  },
  superseded: {
    label: "Source has changed",
    description:
      "The source was revised after this was extracted, so what justified it may no longer be what the source says. A reviewer decides whether the change matters.",
  },
  unknown: {
    label: "Source version not recorded",
    description:
      "This was extracted before source versions were tracked, so which version justified it is unknown. It is not known to be up to date.",
  },
}

/**
 * Compare a record's extraction-time revision against its source's current one.
 *
 * A null `recordRevisionId` is `unknown`, never `current` — that is the whole
 * point of not backfilling it. A null `currentRevisionId` (source not loaded, or
 * a source with no revisions yet) is also `unknown`: we cannot conclude
 * "unchanged" from a comparison we could not make.
 */
export function provenanceState(
  recordRevisionId: number | null | undefined,
  currentRevisionId: number | null | undefined,
): ProvenanceState {
  if (recordRevisionId == null) return "unknown"
  if (currentRevisionId == null) return "unknown"
  return recordRevisionId === currentRevisionId ? "current" : "superseded"
}

/**
 * Resolve `current_revision_id` for many records at once.
 *
 * Records carry `source_revision_id` but `current_revision_id` lives on the
 * source, so the comparison needs both. Per row that is an N+1; this fetches
 * each distinct source once and compares in memory. A source that fails to load
 * is simply absent from the map, which reads as `unknown` rather than as
 * "unchanged".
 */
export async function fetchCurrentRevisionIds(sourceIds: number[]): Promise<Map<number, number | null>> {
  const distinct = Array.from(new Set(sourceIds.filter((id) => Number.isFinite(id))))
  const out = new Map<number, number | null>()
  await Promise.all(
    distinct.map(async (id) => {
      try {
        const source = await apiFetch<KnowledgeSource>(`/knowledge/sources/${encodeURIComponent(String(id))}`)
        out.set(id, source.current_revision_id ?? null)
      } catch {
        // Leave it out: an unresolved source yields `unknown`, not `current`.
      }
    }),
  )
  return out
}

// ── 4 · superseded review tasks ───────────────────────────────────────────────

/** The `metadata_json.reason` the backend writes when a source is superseded. */
export const SOURCE_SUPERSEDED_REASON = "source_superseded"

export type SupersededTaskContext = {
  changedFields: string[]
  extractedFromRevision: number | null
  currentRevision: number | null
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return v != null && typeof v === "object" && !Array.isArray(v)
}

function readNum(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null
}

/**
 * Read the source-superseded context off a review task, or null when the task
 * was raised for some other reason.
 */
export function readSupersededTask(metadataJson: unknown): SupersededTaskContext | null {
  if (!isRecord(metadataJson)) return null
  if (metadataJson.reason !== SOURCE_SUPERSEDED_REASON) return null
  const changed = Array.isArray(metadataJson.changed_fields)
    ? metadataJson.changed_fields.filter((f): f is string => typeof f === "string")
    : []
  return {
    changedFields: changed,
    extractedFromRevision: readNum(metadataJson.extracted_from_revision),
    currentRevision: readNum(metadataJson.current_revision),
  }
}

/**
 * The sentence that keeps an open re-check task from reading as a withdrawn
 * acceptance. A record legitimately reads "Accepted" AND carries this task:
 * superseding raises a question, it does not overturn a decision.
 */
export const SUPERSEDED_TASK_EXPLANATION =
  "This record's own review decision still stands. The source it was drawn from changed afterwards, so someone needs to decide whether that change affects it."
