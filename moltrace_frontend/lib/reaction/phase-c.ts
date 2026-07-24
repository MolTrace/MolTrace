/**
 * Repho Phase C — API helpers + pure readers for the four no-heavy-dependency surfaces:
 * capability readout, yield predictions (R12), route scores (R13), forward checks (R14).
 *
 * Every surface is decision-support: disclaimers render verbatim, human_review_required is
 * always surfaced, and the capability readout is the honest face of the deliberately-unwired
 * heavy paths (route generation, forward generation, GNN training, SDL execution).
 */
import { apiFetch } from "@/lib/api/client"

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v)
}

function readNum(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null
}

function strList(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []
}

// ── Capability readout ───────────────────────────────────────────────────────

export interface ReactionCapability {
  name: string
  enabled: boolean
  available: boolean
  active: boolean
  missingModules: string[]
  reason: string
  engine: string | null
}

export interface CapabilityReadout {
  capabilities: ReactionCapability[]
  disclaimer: string | null
}

export function parseCapabilityReadout(resp: unknown): CapabilityReadout | null {
  if (!isRecord(resp)) return null
  const raw = Array.isArray(resp.capabilities) ? resp.capabilities : []
  return {
    capabilities: raw.filter(isRecord).map((c) => ({
      name: typeof c.name === "string" ? c.name : "",
      enabled: c.enabled === true,
      available: c.available === true,
      active: c.active === true,
      missingModules: strList(c.missing_modules),
      reason: typeof c.reason === "string" ? c.reason : "",
      engine: typeof c.engine === "string" ? c.engine : null,
    })),
    disclaimer: typeof resp.disclaimer === "string" ? resp.disclaimer : null,
  }
}

export interface SdlSiteStatus {
  enabled: boolean
  executionSurfaceWired: boolean
  detail: string | null
  capability: ReactionCapability | null
  disclaimer: string | null
}

export function parseSdlSiteStatus(resp: unknown): SdlSiteStatus | null {
  if (!isRecord(resp)) return null
  const cap = isRecord(resp.capability)
    ? parseCapabilityReadout({ capabilities: [resp.capability] })?.capabilities[0] ?? null
    : null
  return {
    enabled: resp.enabled === true,
    executionSurfaceWired: resp.execution_surface_wired === true,
    detail: typeof resp.detail === "string" ? resp.detail : null,
    capability: cap,
    disclaimer: typeof resp.disclaimer === "string" ? resp.disclaimer : null,
  }
}

export async function getCapabilityReadout(): Promise<unknown> {
  return apiFetch<unknown>("/reaction-capabilities", { method: "GET" })
}

export async function getSdlStatus(): Promise<unknown> {
  return apiFetch<unknown>("/reaction-sdl/status", { method: "GET" })
}

// ── Yield predictions (R12) ──────────────────────────────────────────────────

export interface YieldPredictionItem {
  conditions: Record<string, unknown>
  mean: number | null
  std: number | null
  backend: string | null
  nSamples: number | null
  warnings: string[]
}

export interface YieldPredictionRun {
  id: number | null
  backend: string | null
  trainedN: number | null
  requireVerified: boolean
  predictions: YieldPredictionItem[]
  /** The per-run backend-decision record the disclaimer explicitly points the reader at. */
  capabilityProvenance: Record<string, unknown> | null
  createdAt: string | null
  disclaimer: string | null
}

export function parseYieldPredictionRun(resp: unknown): YieldPredictionRun | null {
  if (!isRecord(resp)) return null
  const raw = Array.isArray(resp.predictions) ? resp.predictions : []
  return {
    id: readNum(resp.id),
    backend: typeof resp.backend === "string" ? resp.backend : null,
    trainedN: readNum(resp.trained_n),
    requireVerified: resp.require_verified === true,
    predictions: raw.filter(isRecord).map((p) => ({
      conditions: isRecord(p.conditions) ? p.conditions : {},
      mean: readNum(p.mean),
      std: readNum(p.std),
      backend: typeof p.backend === "string" ? p.backend : null,
      nSamples: readNum(p.n_samples),
      warnings: strList(p.warnings),
    })),
    capabilityProvenance: isRecord(resp.capability_provenance) ? resp.capability_provenance : null,
    createdAt: typeof resp.created_at === "string" ? resp.created_at : null,
    disclaimer: typeof resp.disclaimer === "string" ? resp.disclaimer : null,
  }
}

export async function postYieldPredictions(
  projectId: number,
  body: { conditions: Record<string, unknown>[]; require_verified?: boolean },
): Promise<unknown> {
  return apiFetch<unknown>(`/reaction-projects/${projectId}/yield-predictions`, {
    method: "POST",
    body,
  })
}

export async function listYieldPredictions(projectId: number): Promise<unknown> {
  return apiFetch<unknown>(`/reaction-projects/${projectId}/yield-predictions`, { method: "GET" })
}

// ── Route scores (R13) ───────────────────────────────────────────────────────

/** A native route-tree node the build-a-tree editor produces (mirrors the request shape). */
export interface RouteNode {
  smiles: string
  children: RouteNode[]
  reagents: string[]
  solvent?: string
}

/** Serialize the editor tree to the request's plain-JSON route shape (drop empty solvent). */
export function routeNodeToJson(node: RouteNode): Record<string, unknown> {
  const out: Record<string, unknown> = {
    smiles: node.smiles.trim(),
    children: node.children.map(routeNodeToJson),
    reagents: node.reagents.map((r) => r.trim()).filter((r) => r !== ""),
  }
  const solvent = (node.solvent ?? "").trim()
  if (solvent) out.solvent = solvent
  return out
}

/** Client-side validation mirroring the backend's 400s: every node needs a SMILES. */
export function validateRouteNode(node: RouteNode, path = "root"): string[] {
  const errors: string[] = []
  if (node.smiles.trim() === "") errors.push(`${path}: SMILES is required`)
  node.children.forEach((c, i) => errors.push(...validateRouteNode(c, `${path}.${i + 1}`)))
  return errors
}

/** A weighted score component as the engine emits it: {value, weight}. */
export interface RouteScoreComponent {
  name: string
  value: number | null
  weight: number | null
}

export interface RouteScoreView {
  id: number | null
  label: string | null
  route: Record<string, unknown>
  routeScore: number | null
  scoreComponents: RouteScoreComponent[]
  worstRisk: string
  requiresExpertReview: boolean
  /** `risk` is never null: a missing/blank risk fails CLOSED to "unknown" (unreviewable). */
  screens: { smiles: string | null; role: string | null; risk: string; requiresExpertReview: boolean }[]
  steps: Record<string, unknown>[]
  stepCount: number | null
  maxDepth: number | null
  startingMaterials: string[]
  meanAtomEconomyPercent: number | null
  meanSolventGreenness: number | null
  warnings: string[]
  humanReviewRequired: boolean
  mermaid: string | null
  createdAt: string | null
  disclaimer: string | null
}

export function parseRouteScoreRecord(resp: unknown): RouteScoreView | null {
  if (!isRecord(resp)) return null
  const score = isRecord(resp.score) ? resp.score : {}
  const safety = isRecord(score.safety) ? score.safety : {}
  const rawScreens = Array.isArray(safety.screens) ? safety.screens : []
  return {
    id: readNum(resp.id),
    label: typeof resp.label === "string" && resp.label ? resp.label : null,
    route: isRecord(resp.route) ? resp.route : {},
    routeScore: readNum(score.route_score),
    // Components arrive as {name: {value, weight}} — unpack so the UI never stringifies an object.
    scoreComponents: isRecord(score.score_components)
      ? Object.entries(score.score_components).map(([name, v]) => ({
          name,
          value: isRecord(v) ? readNum(v.value) : readNum(v),
          weight: isRecord(v) ? readNum(v.weight) : null,
        }))
      : [],
    // Missing/invalid risk reads as "unknown" — the WORST tier (unreviewable), never neutral.
    worstRisk: typeof safety.worst_risk === "string" && safety.worst_risk ? safety.worst_risk : "unknown",
    requiresExpertReview: safety.requires_expert_review !== false,
    screens: rawScreens.filter(isRecord).map((s) => ({
      smiles: typeof s.smiles === "string" ? s.smiles : null,
      role: typeof s.role === "string" ? s.role : null,
      // Fail CLOSED, exactly like worstRisk: absent/blank ⇒ unreviewable, never a missing badge.
      risk:
        typeof s.overall_risk === "string" && s.overall_risk
          ? s.overall_risk
          : typeof s.risk === "string" && s.risk
            ? s.risk
            : "unknown",
      requiresExpertReview: s.requires_expert_review === true,
    })),
    steps: Array.isArray(score.steps) ? score.steps.filter(isRecord) : [],
    stepCount: readNum(score.step_count),
    maxDepth: readNum(score.max_depth),
    startingMaterials: strList(score.starting_materials),
    meanAtomEconomyPercent: readNum(score.mean_atom_economy_percent),
    meanSolventGreenness: readNum(score.mean_solvent_greenness),
    warnings: strList(score.warnings),
    humanReviewRequired: resp.human_review_required !== false && score.human_review_required !== false,
    mermaid: typeof resp.mermaid === "string" && resp.mermaid ? resp.mermaid : null,
    createdAt: typeof resp.created_at === "string" ? resp.created_at : null,
    disclaimer: typeof resp.disclaimer === "string" ? resp.disclaimer : null,
  }
}

/** Route-risk badge class. `unknown` deliberately renders as the WORST (unreviewable) tier —
 *  same red as critical plus an explicit label — never as the shared muted "unknown" style. */
export function routeRiskBadgeClass(risk: string): string {
  switch (risk) {
    case "low":
      return "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
    case "medium":
      return "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
    case "high":
      return "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300"
    case "critical":
      return "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300"
    default: // unknown / anything else: unreviewable — worse than critical
      return "bg-red-100 text-red-900 ring-1 ring-red-400 dark:bg-red-950 dark:text-red-200 dark:ring-red-700"
  }
}

export function routeRiskLabel(risk: string): string {
  return risk === "unknown" || !["low", "medium", "high", "critical"].includes(risk)
    ? `${risk || "unknown"} — unreviewable`
    : risk
}

export async function postRouteScore(
  projectId: number,
  body: { route: Record<string, unknown>; label?: string; route_format?: string },
): Promise<unknown> {
  return apiFetch<unknown>(`/reaction-projects/${projectId}/route-scores`, { method: "POST", body })
}

export async function listRouteScores(projectId: number): Promise<unknown> {
  return apiFetch<unknown>(`/reaction-projects/${projectId}/route-scores`, { method: "GET" })
}

// ── Forward checks (R14) ─────────────────────────────────────────────────────

export interface ForwardCheckView {
  id: number | null
  label: string | null
  reactantsSmiles: string[]
  reagentsSmiles: string[]
  productsSmiles: string[]
  confidence: number | null
  overallRisk: string
  requiresExpertReview: boolean
  energeticGroupsFound: string[]
  solventGreenness: number | null
  warnings: string[]
  humanReviewRequired: boolean
  createdAt: string | null
  disclaimer: string | null
}

export function parseForwardCheckRecord(resp: unknown): ForwardCheckView | null {
  if (!isRecord(resp)) return null
  const result = isRecord(resp.result) ? resp.result : {}
  const safety = isRecord(result.safety) ? result.safety : {}
  return {
    id: readNum(resp.id),
    label: typeof resp.label === "string" && resp.label ? resp.label : null,
    reactantsSmiles: strList(resp.reactants_smiles),
    reagentsSmiles: strList(resp.reagents_smiles),
    productsSmiles: strList(result.products_smiles),
    confidence: readNum(result.confidence),
    overallRisk:
      typeof safety.overall_risk === "string" && safety.overall_risk ? safety.overall_risk : "unknown",
    requiresExpertReview: safety.requires_expert_review !== false,
    energeticGroupsFound: strList(safety.energetic_groups_found),
    solventGreenness: readNum(result.solvent_greenness),
    warnings: strList(result.warnings),
    humanReviewRequired: resp.human_review_required !== false && result.human_review_required !== false,
    createdAt: typeof resp.created_at === "string" ? resp.created_at : null,
    disclaimer: typeof resp.disclaimer === "string" ? resp.disclaimer : null,
  }
}

/** Parse a comma/newline-separated SMILES textarea into a clean list. */
export function parseSmilesList(text: string): string[] {
  return (text ?? "")
    .split(/[,\n]/)
    .map((s) => s.trim())
    .filter((s) => s !== "")
}

export async function postForwardCheck(
  projectId: number,
  body: {
    reactants_smiles: string[]
    products_smiles: string[]
    reagents_smiles?: string[]
    confidence?: number
    label?: string
  },
): Promise<unknown> {
  return apiFetch<unknown>(`/reaction-projects/${projectId}/forward-checks`, {
    method: "POST",
    body,
  })
}

export async function listForwardChecks(projectId: number): Promise<unknown> {
  return apiFetch<unknown>(`/reaction-projects/${projectId}/forward-checks`, { method: "GET" })
}
