// Repho R4 — regulatory-compliance evaluation (closed-loop, read side).
//
// Evaluates a project's RECORDED experiment outcomes against its ACTIVE injected
// regulatory constraints (those carrying a numeric limit), and reports which
// experiments breach a limit — with provenance back to the regulatory source.
//
// HONEST SCOPING: the Bayesian optimizer scalarizes to a single score, so this is
// evaluated against *measured outcomes*, NOT at recommendation time. Never present
// it as "the optimizer filtered these." It is the enforced end of the
// Regentry→Repho loop, the read-side companion to the constraints editor.
//
// Owner-scoped GET (non-owner ⇒ non-leaking 404). `violations` are free-form
// engine objects — read defensively.

import { apiFetch } from "@/lib/api/client"

export type ComplianceRowStatus = "non_compliant" | "flagged" | "within_limits"

export type ComplianceViolation = {
  constraintId: number | null
  constraintType: string | null
  objectiveField: string | null
  comparator: string | null // "max" | "min"
  predictedValue: number | null
  limitValue: number | null
  limitUnit: string | null
  basis: string | null
  severity: string | null // info | warning | high | critical
  isHard: boolean
  sourceActionItemIds: number[]
}

export type ComplianceItem = {
  experimentId: number | null
  experimentCode: string
  status: string
  feasible: boolean
  hardBlock: boolean
  penalty: number | null
  violations: ComplianceViolation[]
  unmeasured: string[]
}

export type ComplianceReport = {
  reactionProjectId: number | null
  enforcedConstraintCount: number
  activeConstraintIds: number[]
  constraintBases: string[]
  experimentsEvaluated: number
  nonCompliantExperimentCount: number
  items: ComplianceItem[]
  notes: string[]
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
function readStr(v: unknown): string | null {
  return typeof v === "string" && v.trim() !== "" ? v : null
}
function readStrArray(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []
}
function readNumArray(v: unknown): number[] {
  return Array.isArray(v) ? v.map(readNum).filter((n): n is number => n != null) : []
}

function parseViolation(v: unknown): ComplianceViolation | null {
  if (!isRecord(v)) return null
  return {
    constraintId: readNum(v.constraint_id),
    constraintType: readStr(v.constraint_type),
    objectiveField: readStr(v.objective_field),
    comparator: readStr(v.comparator),
    predictedValue: readNum(v.predicted_value),
    limitValue: readNum(v.limit_value),
    limitUnit: readStr(v.limit_unit),
    basis: readStr(v.basis),
    severity: readStr(v.severity),
    isHard: v.is_hard === true,
    sourceActionItemIds: readNumArray(v.source_action_item_ids),
  }
}

function parseItem(v: unknown): ComplianceItem | null {
  if (!isRecord(v)) return null
  const experimentId = readNum(v.experiment_id)
  return {
    experimentId,
    experimentCode: readStr(v.experiment_code) ?? (experimentId != null ? `#${experimentId}` : "—"),
    status: readStr(v.status) ?? "unknown",
    feasible: v.feasible !== false,
    hardBlock: v.hard_block === true,
    penalty: readNum(v.penalty),
    violations: Array.isArray(v.violations)
      ? v.violations.map(parseViolation).filter((x): x is ComplianceViolation => x != null)
      : [],
    unmeasured: readStrArray(v.unmeasured),
  }
}

export function parseComplianceReport(raw: unknown): ComplianceReport {
  const r = isRecord(raw) ? raw : {}
  return {
    reactionProjectId: readNum(r.reaction_project_id),
    enforcedConstraintCount: readNum(r.enforced_constraint_count) ?? 0,
    activeConstraintIds: readNumArray(r.active_constraint_ids),
    constraintBases: readStrArray(r.constraint_bases),
    experimentsEvaluated: readNum(r.experiments_evaluated) ?? 0,
    nonCompliantExperimentCount: readNum(r.non_compliant_experiment_count) ?? 0,
    items: Array.isArray(r.items)
      ? r.items.map(parseItem).filter((x): x is ComplianceItem => x != null)
      : [],
    notes: readStrArray(r.notes),
  }
}

/** Per-experiment row status: hard violation → non-compliant; soft violation →
 *  flagged; otherwise within limits. A field with a limit but no measured value
 *  is NEVER counted as passing (see `unmeasured`). */
export function itemStatus(item: ComplianceItem): ComplianceRowStatus {
  if (item.hardBlock) return "non_compliant"
  if (item.violations.length > 0) return "flagged"
  return "within_limits"
}

// ── API ──────────────────────────────────────────────────────────────────────
export async function getRegulatoryCompliance(projectId: number): Promise<ComplianceReport> {
  return parseComplianceReport(
    await apiFetch<unknown>(`/reaction-projects/${projectId}/regulatory-compliance`, { method: "GET" }),
  )
}

// ── theme-safe styling (semantic classes carry their own dark: variant) ────────
export const COMPLIANCE_STATUS: Record<
  ComplianceRowStatus,
  { label: string; badgeClass: string }
> = {
  non_compliant: {
    label: "Non-compliant",
    badgeClass: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  },
  flagged: {
    label: "Flagged",
    badgeClass: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  },
  within_limits: {
    label: "Within limits",
    badgeClass: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  },
}

export const SEVERITY_BADGE_CLASS: Record<string, string> = {
  critical: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  high: "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300",
  warning: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  info: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
}
