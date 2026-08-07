import type { components } from "@/src/lib/api/schema"

/**
 * Reading `GET /audit/{subject_type}/{subject_id}/verify`.
 *
 * The interpretation lives here rather than in the component so the rules can be
 * tested directly — every one of them exists because the obvious rendering
 * misleads.
 */

export type SubjectAuditChainVerification = components["schemas"]["SubjectAuditChainVerification"]

/** Only these two are verifiable. A spectroscopy session has its own review surface. */
export type TraceableSubjectType = "regulatory_dossier" | "reaction_project"

export type TraceableSubject = { type: TraceableSubjectType; id: number }

/**
 * `unchecked` is deliberately NOT a variant of `broken` or of `verified`.
 *
 * `entry_count: 0` comes back with `detail: "no_chained_entries"`, and the one
 * thing it must never render as is a pass. Nothing was checked, so nothing is
 * established — a green tick there would be the single most misleading pixel in
 * the product.
 */
export type ChainOutcome = "verified" | "broken" | "unchecked"

export function chainOutcome(v: SubjectAuditChainVerification): ChainOutcome {
  if (v.entry_count === 0) return "unchecked"
  return v.ok ? "verified" : "broken"
}

/**
 * Plain language for a machine-readable break kind.
 *
 * Keyed off `break_kind` / `chain_break_kind` and NEVER off `detail`: `detail` is
 * prose the backend is free to reword, and string-matching it is how a client
 * silently starts reporting the wrong cause after a harmless copy edit.
 *
 * An unrecognised kind returns null so the caller states that the trail failed
 * without inventing a reason for it.
 */
const BREAK_KIND_COPY: Record<string, string> = {
  entry_hash_mismatch: "An entry about this record was altered after it was written.",
  sequence_gap: "An entry is missing from the chain — something was removed.",
  prev_hash_mismatch: "Entries no longer link in their original order.",
}

export function describeBreak(v: SubjectAuditChainVerification): string | null {
  const kind = v.break_kind ?? v.chain_break_kind
  if (!kind) return null
  return BREAK_KIND_COPY[kind] ?? null
}

/**
 * The two findings, reported separately and never merged.
 *
 * `content_ok` is provable from the subject's own entries: each still hashes to
 * the digest stored with it, so none was altered. `chain_ok` needs the global
 * walk, and it is the only thing that can establish an entry about this subject
 * was not REMOVED — entries carry no per-subject sequence, so a deletion leaves
 * no gap inside the subject's own view.
 *
 * Collapsing these into one indicator would claim the slice established
 * something it cannot. Hence two rows, always, each saying what it covers.
 */
export type ChainFinding = { label: string; ok: boolean; covers: string }

export function chainFindings(v: SubjectAuditChainVerification): ChainFinding[] {
  return [
    {
      label: "Nothing was altered",
      ok: v.content_ok,
      covers: "Every recorded entry about this record still matches the digest stored with it.",
    },
    {
      label: "Nothing was removed or reordered",
      ok: v.chain_ok,
      covers:
        "Checked against the full chain, because a removed entry leaves no gap in this record's own view.",
    },
  ]
}
