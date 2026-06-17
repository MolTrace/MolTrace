import { apiFetch } from "@/lib/api/client"
import type { components } from "@/src/lib/api/schema"

export type GreenAssessment = components["schemas"]["ReactionGreenAssessment"]
export type GreenMetricsRequest = components["schemas"]["ReactionGreenMetricsRequest"]
export type GreenComponent = components["schemas"]["ReactionGreenComponent"]
export type GreenComponentRole = GreenComponent["role"]
export type GreenProfile = components["schemas"]["ReactionGreenProfile"]
export type GreenProfileCreate = components["schemas"]["ReactionGreenProfileCreate"]
export type GreenProfileUpdate = components["schemas"]["ReactionGreenProfileUpdate"]
export type GreenCompareResult = components["schemas"]["ReactionGreenCompareResult"]
export type GreenCompareEntry = components["schemas"]["ReactionGreenCompareEntry"]

export const GREEN_COMPONENT_ROLES: GreenComponentRole[] = [
  "reactant",
  "reagent",
  "catalyst",
  "solvent",
  "workup",
  "other",
]

/** The headline green metrics, in display order. `better` drives best-in-compare
 *  highlighting (min for E-factor/PMI; max for the rest). Keys are the
 *  `metrics_json` keys the deterministic backend returns. */
export const GREEN_METRICS: {
  key: string
  label: string
  unit?: string
  digits: number
  better: "low" | "high"
  help: string
}[] = [
  { key: "green_score", label: "Green score", digits: 1, better: "high", help: "Composite 0–100 greenness (higher is greener)." },
  { key: "e_factor", label: "E-factor", digits: 2, better: "low", help: "kg waste per kg product (lower is greener)." },
  { key: "pmi", label: "PMI", digits: 2, better: "low", help: "Process mass intensity: total input mass per kg product." },
  { key: "atom_economy_percent", label: "Atom economy", unit: "%", digits: 1, better: "high", help: "Fraction of reactant mass retained in the product." },
  { key: "rme_percent", label: "RME", unit: "%", digits: 1, better: "high", help: "Reaction mass efficiency: product mass / total input mass." },
]

/** Read a numeric metric from the opaque `metrics_json`/outcome dict. */
export function readGreenMetric(metrics: Record<string, unknown> | null | undefined, key: string): number | null {
  const v = metrics?.[key]
  return typeof v === "number" && Number.isFinite(v) ? v : null
}

export function formatGreenMetric(value: number | null, digits: number, unit?: string): string {
  if (value == null) return "—"
  return `${value.toLocaleString(undefined, { maximumFractionDigits: digits })}${unit ?? ""}`
}

const projectBase = (projectId: number) => `/reaction-projects/${projectId}`

export async function computeGreenMetrics(projectId: number, experimentId: number, body: GreenMetricsRequest) {
  return apiFetch<GreenAssessment>(`${projectBase(projectId)}/experiments/${experimentId}/green-metrics`, {
    method: "POST",
    body,
  })
}

export async function getGreenMetrics(projectId: number, experimentId: number) {
  return apiFetch<GreenAssessment>(`${projectBase(projectId)}/experiments/${experimentId}/green-metrics`, {
    method: "GET",
  })
}

export async function getGreenProfile(projectId: number) {
  return apiFetch<GreenProfile>(`${projectBase(projectId)}/green-profile`, { method: "GET" })
}

export async function createGreenProfile(projectId: number, body: GreenProfileCreate) {
  return apiFetch<GreenProfile>(`${projectBase(projectId)}/green-profile`, { method: "POST", body })
}

export async function updateGreenProfile(projectId: number, body: GreenProfileUpdate) {
  return apiFetch<GreenProfile>(`${projectBase(projectId)}/green-profile`, { method: "PATCH", body })
}

export async function compareGreenMetrics(projectId: number, experimentIds: number[]) {
  return apiFetch<GreenCompareResult>(`${projectBase(projectId)}/green-compare`, {
    method: "POST",
    body: { experiment_ids: experimentIds },
  })
}

/** The green optimization objectives added in R1 (selectable in objective profiles). */
export const GREEN_OBJECTIVES = [
  { value: "minimize_e_factor", label: "Minimize E-factor", weightKey: "e_factor_weight" },
  { value: "maximize_atom_economy", label: "Maximize atom economy", weightKey: "atom_economy_weight" },
  { value: "maximize_green_score", label: "Maximize green score", weightKey: "green_score_weight" },
] as const
