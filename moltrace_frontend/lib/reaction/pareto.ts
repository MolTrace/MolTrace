// Repho R2 — multi-objective Pareto front + hypervolume.
//
// The backend rides this inside an existing BO run's `diagnostics_json` (no new
// endpoint, no schema change): `run.diagnostics_json.pareto_front`. It is `null`
// for single-objective campaigns or when there isn't enough multi-objective data.
// Everything here is read defensively — `diagnostics_json` is a free-form object.

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

export type ParetoMember = {
  experimentId: number | null
  experimentCode: string | null
  /** Raw outcome values keyed by objective name (impurity is real %, not inverted). */
  objectives: Record<string, number>
  nonDominated: boolean
}

export type ParetoFront = {
  objectives: string[]
  hypervolume: number | null
  hypervolumeMethod: string | null
  referencePoint: number[] | null
  paretoSize: number | null
  evaluatedExperimentCount: number | null
  kneeExperimentId: number | null
  members: ParetoMember[]
  note: string | null
}

function readObjectiveMap(v: unknown): Record<string, number> {
  if (!isRecord(v)) return {}
  const out: Record<string, number> = {}
  for (const [k, raw] of Object.entries(v)) {
    const n = readNum(raw)
    if (n != null) out[k] = n
  }
  return out
}

function readMember(v: unknown): ParetoMember | null {
  if (!isRecord(v)) return null
  return {
    experimentId: readNum(v.experiment_id),
    experimentCode: readStr(v.experiment_code),
    objectives: readObjectiveMap(v.objectives),
    nonDominated: v.non_dominated === true,
  }
}

/** The diagnostics object that may carry `pareto_front` (run.diagnostics_json). */
export function readParetoFront(diagnosticsJson: unknown): ParetoFront | null {
  if (!isRecord(diagnosticsJson)) return null
  const pf = diagnosticsJson.pareto_front
  if (!isRecord(pf)) return null

  const objectives = Array.isArray(pf.objectives)
    ? pf.objectives.filter((o): o is string => typeof o === "string")
    : []
  const members = Array.isArray(pf.members)
    ? pf.members.map(readMember).filter((m): m is ParetoMember => m != null)
    : []

  // A usable front needs at least the objective dimensions and some members.
  if (objectives.length === 0 || members.length === 0) return null

  const referencePoint = Array.isArray(pf.reference_point)
    ? pf.reference_point.map(readNum).filter((n): n is number => n != null)
    : null

  return {
    objectives,
    hypervolume: readNum(pf.hypervolume),
    hypervolumeMethod: readStr(pf.hypervolume_method),
    referencePoint: referencePoint && referencePoint.length ? referencePoint : null,
    paretoSize: readNum(pf.pareto_size),
    evaluatedExperimentCount: readNum(pf.evaluated_experiment_count),
    kneeExperimentId: readNum(pf.knee_experiment_id),
    members,
    note: readStr(pf.note),
  }
}

/** Read the Pareto front from a BO run record (diagnostics_json or legacy diagnostics). */
export function paretoFrontFromRun(run: unknown): ParetoFront | null {
  if (!isRecord(run)) return null
  return readParetoFront(run.diagnostics_json) ?? readParetoFront(run.diagnostics)
}

/** Experiment ids that sit on the Pareto front (non_dominated === true). */
export function nonDominatedExperimentIds(front: ParetoFront | null): Set<number> {
  const ids = new Set<number>()
  if (!front) return ids
  for (const m of front.members) {
    if (m.nonDominated && m.experimentId != null) ids.add(m.experimentId)
  }
  return ids
}

/** A stable key for an objective set, so we only trend hypervolume across runs of the SAME set. */
export function objectivesKey(objectives: string[]): string {
  return [...objectives].sort().join("|")
}

export type HypervolumePoint = { boRunId: number | null; hypervolume: number; objectivesKey: string }

function readBoRunId(run: Record<string, unknown>): number | null {
  return readNum(run.bo_run_id) ?? readNum(run.id) ?? readNum(run.run_id)
}

/**
 * Hypervolume across a project's BO runs, oldest→newest, restricted to runs whose
 * objective set matches `forKey` (the indicator is only comparable within one set).
 */
export function hypervolumeTrend(runs: unknown[], forKey: string): HypervolumePoint[] {
  const pts: HypervolumePoint[] = []
  for (const run of runs) {
    if (!isRecord(run)) continue
    const front = paretoFrontFromRun(run)
    if (!front || front.hypervolume == null) continue
    const key = objectivesKey(front.objectives)
    if (key !== forKey) continue
    pts.push({ boRunId: readBoRunId(run), hypervolume: front.hypervolume, objectivesKey: key })
  }
  pts.sort((a, b) => (a.boRunId ?? 0) - (b.boRunId ?? 0))
  return pts
}

/** Compact hypervolume label — the indicator can span many orders of magnitude. */
export function formatHypervolume(n: number | null): string {
  if (n == null || !Number.isFinite(n)) return "—"
  if (n !== 0 && (Math.abs(n) >= 1e6 || Math.abs(n) < 1e-3)) return n.toExponential(2)
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

/** Human label for the hypervolume method tag. */
export function hypervolumeMethodLabel(method: string | null): string {
  if (!method) return ""
  if (method === "exact_2d") return "exact (2-D)"
  if (method === "monte_carlo") return "Monte Carlo"
  return method
}
