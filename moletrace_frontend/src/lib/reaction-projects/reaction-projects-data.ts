import { apiFetch } from "@/lib/api/client"

export type ReactionObjectiveValue =
  | "maximize_yield"
  | "maximize_selectivity"
  | "minimize_impurity"
  | "maximize_conversion"
  | "multi_objective"

export type ReactionProjectRow = {
  id: number
  name: string
  objective: ReactionObjectiveValue | string
  status: string
  updated_at: string
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return v != null && typeof v === "object" && !Array.isArray(v)
}

function readNum(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v
  return null
}

export function parseReactionProjectList(raw: unknown): ReactionProjectRow[] {
  if (!Array.isArray(raw)) return []
  const out: ReactionProjectRow[] = []
  for (const item of raw) {
    if (!isRecord(item)) continue
    const id = readNum(item.id)
    const name = typeof item.name === "string" ? item.name : null
    if (id == null || !name) continue
    const objective =
      typeof item.objective === "string" ? item.objective : "maximize_yield"
    const status = typeof item.status === "string" ? item.status : "draft"
    const updated_at =
      typeof item.updated_at === "string"
        ? item.updated_at
        : typeof item.updated_at === "number"
          ? new Date(item.updated_at).toISOString()
          : ""
    out.push({ id, name, objective, status, updated_at })
  }
  return out
}

export type ProjectCounts = {
  experiments: number
  experimentsCompleted: number
  recommendations: number
  recommendationsPendingReview: number
  bestYieldPercent: number | null
}

export function parseExperimentYield(exp: unknown): number | null {
  if (!isRecord(exp)) return null
  const outcome = exp.outcome
  if (isRecord(outcome)) {
    const y = readNum(outcome.yield_percent)
    if (y != null) return y
  }
  const oj = exp.outcome_json
  if (isRecord(oj)) {
    const y = readNum(oj.yield_percent)
    if (y != null) return y
  }
  return null
}

export async function fetchProjectCounts(projectId: number): Promise<ProjectCounts | null> {
  try {
    const [exRaw, recRaw] = await Promise.all([
      apiFetch<unknown>(`/reaction-projects/${projectId}/experiments`, { method: "GET" }),
      apiFetch<unknown>(`/reaction-projects/${projectId}/recommendations`, { method: "GET" }),
    ])
    const experiments = Array.isArray(exRaw) ? exRaw : []
    let experimentsCompleted = 0
    let bestYield: number | null = null
    for (const exp of experiments) {
      if (!isRecord(exp)) continue
      if (exp.status === "completed") {
        experimentsCompleted += 1
        const y = parseExperimentYield(exp)
        if (y != null && (bestYield == null || y > bestYield)) bestYield = y
      }
    }
    const recs = Array.isArray(recRaw) ? recRaw : []
    let recommendationsPendingReview = 0
    for (const r of recs) {
      if (!isRecord(r)) continue
      if (r.status === "proposed") recommendationsPendingReview += 1
    }
    return {
      experiments: experiments.length,
      experimentsCompleted,
      recommendations: recs.length,
      recommendationsPendingReview,
      bestYieldPercent: bestYield,
    }
  } catch {
    return null
  }
}

export async function enrichProjectsWithCounts(
  projects: ReactionProjectRow[],
  concurrency = 6,
): Promise<Map<number, ProjectCounts>> {
  const map = new Map<number, ProjectCounts>()
  const batchSize = Math.max(1, concurrency)
  for (let i = 0; i < projects.length; i += batchSize) {
    const chunk = projects.slice(i, i + batchSize)
    const results = await Promise.all(
      chunk.map(async (p) => {
        const c = await fetchProjectCounts(p.id)
        return c ? ([p.id, c] as const) : null
      }),
    )
    for (const r of results) {
      if (r) map.set(r[0], r[1])
    }
  }
  return map
}
