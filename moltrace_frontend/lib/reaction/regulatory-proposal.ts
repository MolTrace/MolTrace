// Repho — proposal-time regulatory verdict, carried on each BO acquisition candidate.
//
// The read-side companion to `regulatory-compliance.ts`. Same `ConstraintViolation`
// wire shape, different moment: this one rides on a *proposal* (an acquisition
// candidate the optimizer ranked), the other on a *measured outcome*.
//
// HONEST SCOPING — the one thing this module exists to get right:
//
//   The surrogate scores a candidate on a single SCALARIZED objective, so it
//   supplies none of the per-field values a limit is written against. Today
//   essentially every limit therefore lands in `unmeasured`, and NOTHING is
//   filtered at proposal time.
//
//   `feasible` means "no HARD violation" — it does NOT mean "checked and passed".
//   A verdict with `feasible: true` and a non-empty `unmeasured` is NOT CHECKED,
//   and must never render as cleared. `applied_constraint_ids` is no help either:
//   the engine appends a constraint id BEFORE testing whether the field is
//   predictable, so it counts limits that went on to land in `unmeasured`.
//
//   The only genuine pass is: no violations AND nothing unmeasured.
//
// The shape rides inside `metadata_json.regulatory` (typed `dict[str, Any]`
// server-side, so untyped here) — read defensively.

import type { ComplianceViolation } from "@/lib/reaction/regulatory-compliance"
import { parseViolation } from "@/lib/reaction/regulatory-compliance"

/** Ranked most-severe first. `not_checked` is a distinct state from `within_limits`
 *  on purpose — collapsing the two is the failure this module guards against. */
export type ProposalRegulatoryState = "blocked" | "flagged" | "not_checked" | "within_limits"

export type CandidateRegulatory = {
  feasible: boolean
  hardBlock: boolean
  penalty: number | null
  violations: ComplianceViolation[]
  /** objective_fields that carry a limit but had no predicted value. */
  unmeasured: string[]
  appliedConstraintIds: number[]
}

export type RunRegulatorySummary = {
  /** Candidates that survived every filter. `null` on runs recorded before the
   *  seam landed — unknown, never "nothing was blocked". */
  feasibleCount: number | null
  blockedCount: number
  /** False when the run predates the seam, so the UI can say "unknown". */
  feasibilityKnown: boolean
  /** `succeeded` alone does NOT mean this. A run whose every candidate was
   *  filtered by a hard limit reports zero feasible candidates. */
  readyToSchedule: boolean
  /** The run-level "these limits could not be checked" sentence, pulled out so a
   *  caller can render it ABOVE the figures it qualifies. */
  uncheckedWarning: string | null
  /** Every other run warning, order preserved. */
  otherWarnings: string[]
}

// ── defensive readers ─────────────────────────────────────────────────────────
function isRecord(v: unknown): v is Record<string, unknown> {
  return v != null && typeof v === "object" && !Array.isArray(v)
}
function readNum(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v
  if (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v))) return Number(v)
  return null
}
function readStrArray(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []
}
function readNumArray(v: unknown): number[] {
  return Array.isArray(v) ? v.map(readNum).filter((n): n is number => n != null) : []
}

/** Parse `metadata_json.regulatory`. Returns null when the project had no active
 *  enforceable constraints (the engine omits the key entirely) — which is a
 *  different thing from "checked and clean", and callers must treat it as such. */
export function parseCandidateRegulatory(metadataJson: unknown): CandidateRegulatory | null {
  if (!isRecord(metadataJson)) return null
  const r = metadataJson.regulatory
  if (!isRecord(r)) return null
  return {
    feasible: r.feasible !== false,
    hardBlock: r.hard_block === true,
    penalty: readNum(r.penalty),
    violations: Array.isArray(r.violations)
      ? r.violations.map(parseViolation).filter((x): x is ComplianceViolation => x != null)
      : [],
    unmeasured: readStrArray(r.unmeasured),
    appliedConstraintIds: readNumArray(r.applied_constraint_ids),
  }
}

/** Hard violation → blocked; soft violation → flagged; anything unmeasured →
 *  not_checked. `within_limits` requires that every limit actually got a value
 *  AND none was breached — see the module header for why nothing weaker works. */
export function proposalRegulatoryState(reg: CandidateRegulatory): ProposalRegulatoryState {
  if (reg.hardBlock) return "blocked"
  if (reg.violations.length > 0) return "flagged"
  if (reg.unmeasured.length > 0) return "not_checked"
  return "within_limits"
}

// ── the run-level view ────────────────────────────────────────────────────────

/** Substring of the engine's verbatim unchecked-limits sentence. Matched on the
 *  consequence clause rather than the whole sentence so a reworded preamble or a
 *  different field list still hoists it above the figures. */
const UNCHECKED_WARNING_MARKER = "were not applied to ranking"

function readRunWarnings(run: Record<string, unknown>): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const key of ["warnings", "warnings_json"] as const) {
    for (const w of readStrArray(run[key])) {
      if (!seen.has(w)) {
        seen.add(w)
        out.push(w)
      }
    }
  }
  return out
}

function readRunDiagnostics(run: Record<string, unknown>): Record<string, unknown> {
  if (isRecord(run.diagnostics_json)) return run.diagnostics_json
  if (isRecord(run.diagnostics)) return run.diagnostics
  return {}
}

export function readRunRegulatorySummary(run: unknown): RunRegulatorySummary {
  const r = isRecord(run) ? run : {}
  const diag = readRunDiagnostics(r)
  const rawFeasible = diag.feasible_candidate_count
  // Absent (older run) or non-numeric ⇒ unknown. Reading absence as zero-blocked
  // would let a run written by an older path present itself as all-clear.
  const feasibleCount = readNum(rawFeasible)
  const feasibilityKnown = rawFeasible != null && feasibleCount != null
  const warnings = readRunWarnings(r)
  const status = typeof r.status === "string" ? r.status.trim().toLowerCase() : ""

  return {
    feasibleCount: feasibilityKnown ? feasibleCount : null,
    blockedCount: readNum(diag.regulatory_blocked_candidate_count) ?? 0,
    feasibilityKnown,
    readyToSchedule: status === "succeeded" && feasibilityKnown && (feasibleCount ?? 0) > 0,
    uncheckedWarning: warnings.find((w) => w.includes(UNCHECKED_WARNING_MARKER)) ?? null,
    otherWarnings: warnings.filter((w) => !w.includes(UNCHECKED_WARNING_MARKER)),
  }
}

/** Index a run's acquisition candidates by every id a rendered row might carry.
 *
 *  The candidate is where the verdict lives, but the batch table renders
 *  RECOMMENDATION rows — a different id space. The engine writes both ids into
 *  the candidate summary (`recommendation_id`, `acquisition_candidate_id`), so
 *  index by both and let the caller look up by whichever it holds. */
export function candidateRegulatoryById(run: unknown): Map<number, CandidateRegulatory> {
  const out = new Map<number, CandidateRegulatory>()
  const r = isRecord(run) ? run : {}
  const lists = [r.recommendations_json, r.recommendations]
  for (const list of lists) {
    if (!Array.isArray(list)) continue
    for (const row of list) {
      if (!isRecord(row)) continue
      const md = isRecord(row.metadata_json) ? row.metadata_json : null
      const reg = parseCandidateRegulatory(md)
      if (reg == null) continue
      for (const key of [
        readNum(row.recommendation_id),
        readNum(md?.recommendation_id),
        readNum(row.acquisition_candidate_id),
        readNum(row.id),
      ]) {
        if (key != null && !out.has(key)) out.set(key, reg)
      }
    }
  }
  return out
}

/** Look a row's verdict up by any id it carries, preferring the recommendation id. */
export function candidateRegulatoryForRow(
  row: Record<string, unknown>,
  index: Map<number, CandidateRegulatory>,
): CandidateRegulatory | null {
  const md = isRecord(row.metadata_json) ? row.metadata_json : null
  for (const key of [
    readNum(row.id),
    readNum(md?.recommendation_id),
    readNum(md?.acquisition_candidate_id),
    readNum(row.acquisition_candidate_id),
  ]) {
    if (key == null) continue
    const hit = index.get(key)
    if (hit != null) return hit
  }
  return null
}

// ── display ───────────────────────────────────────────────────────────────────

/** Wire keys are never shown to a user (CLAUDE.md). The engine's own
 *  `violation_reasons` strings embed the raw snake_case `objective_field`, so the
 *  UI rebuilds the sentence from the structured fields instead of printing them. */
const FIELD_LABELS: Record<string, string> = {
  impurity_percent: "Impurity",
  residual_solvent_ppm: "Residual solvent",
  nitrosamine_ng_per_day: "Nitrosamine exposure",
  nmr_purity_percent: "qNMR purity",
}

const UNIT_SUFFIXES = ["_percent", "_ppm", "_ng_per_day"]

export function humanizeObjectiveField(field: string | null): string {
  if (!field) return "Value"
  const known = FIELD_LABELS[field]
  if (known) return known
  let base = field
  for (const suffix of UNIT_SUFFIXES) {
    if (base.endsWith(suffix)) {
      base = base.slice(0, -suffix.length)
      break
    }
  }
  const words = base.split("_").filter(Boolean).join(" ").trim()
  if (!words) return "Value"
  return words.charAt(0).toUpperCase() + words.slice(1)
}

export function formatLimitUnit(unit: string | null): string {
  switch (unit) {
    case "percent":
      return "%"
    case "ppm":
      return " ppm"
    case "ng_per_day":
      return " ng/day"
    default:
      return unit ? ` ${unit}` : ""
  }
}

function formatValue(value: number | null, unit: string | null): string {
  if (value == null) return "—"
  return `${value}${formatLimitUnit(unit)}`
}

/** A human sentence built from the structured violation, e.g.
 *  "Impurity 0.42% exceeds the 0.15% limit (ICH Q3B(R2) identification threshold)."
 *  Deliberately NOT the engine's `violation_reasons`, which carry wire keys. */
export function violationSentence(v: ComplianceViolation): string {
  const label = humanizeObjectiveField(v.objectiveField)
  const relation = v.comparator === "min" ? "falls below" : "exceeds"
  const predicted = formatValue(v.predictedValue, v.limitUnit)
  const limit = formatValue(v.limitValue, v.limitUnit)
  const head = `${label} ${predicted} ${relation} the ${limit} limit`
  return v.basis ? `${head} (${v.basis}).` : `${head}.`
}

export const PROPOSAL_REGULATORY_STATE: Record<
  ProposalRegulatoryState,
  { label: string; badgeClass: string; description: string }
> = {
  blocked: {
    label: "Blocked",
    badgeClass: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
    description: "A hard limit was breached; this candidate was filtered out of the ranking.",
  },
  flagged: {
    label: "Flagged",
    badgeClass: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
    description: "A limit was breached below the hard tier; the candidate was ranked down, not removed.",
  },
  not_checked: {
    label: "Not checked",
    badgeClass: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
    description:
      "A limit applies but the proposal carries no value to compare against it. Not a pass — checked against measured results once the experiment is recorded.",
  },
  within_limits: {
    label: "Within limits",
    badgeClass: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
    description: "Every applicable limit had a value to compare, and none was breached.",
  },
}
