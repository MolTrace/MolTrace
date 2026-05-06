/**
 * Compact ML Model Factory rollup for the v0 dashboard using:
 * GET /ml/model-health, GET /ml/deployment-candidates, GET /ml/evaluation-runs
 * No secrets or raw payloads — counts and short hints only.
 */

import { apiFetch } from "@/lib/api/client"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readNumLoose(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return Math.floor(v)
  if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Math.floor(Number(v))
  return null
}

function readTopLevelInt(raw: unknown, keys: string[]): number | null {
  if (!isRecord(raw)) return null
  for (const k of keys) {
    const n = readNumLoose(raw[k])
    if (n != null && n >= 0) return n
  }
  return null
}

function readMetadataInt(raw: unknown, keys: string[]): number | null {
  if (!isRecord(raw)) return null
  const m = raw.metadata_json
  if (!isRecord(m)) return null
  for (const k of keys) {
    const n = readNumLoose(m[k])
    if (n != null && n >= 0) return n
  }
  return null
}

function asRecordArray(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord) as Record<string, unknown>[]
  if (!isRecord(data)) return []
  for (const k of ["items", "results", "rows", "data", "candidates", "deployment_candidates", "evaluation_runs"]) {
    const v = data[k]
    if (Array.isArray(v)) return v.filter(isRecord) as Record<string, unknown>[]
  }
  return []
}

const OPEN_DEPLOY = new Set(["proposed", "in_review"])

function countOpenDeploymentCandidates(rows: Record<string, unknown>[]): number {
  let n = 0
  for (const r of rows) {
    const st = String(r.status ?? "")
      .trim()
      .toLowerCase()
    if (OPEN_DEPLOY.has(st)) n += 1
  }
  return n
}

function countFailedEvaluations(rows: Record<string, unknown>[]): number {
  let n = 0
  for (const r of rows) {
    const st = String(r.status ?? "")
      .trim()
      .toLowerCase()
    if (st === "failed") n += 1
  }
  return n
}

function countDriftHintFromWarnings(warnings: unknown): number {
  if (!Array.isArray(warnings)) return 0
  let n = 0
  for (const w of warnings) {
    if (typeof w === "string" && /drift|dataset|skew|shift/i.test(w)) n += 1
  }
  return n
}

function countErrorAnalysisHintFromWarnings(warnings: unknown): number {
  if (!Array.isArray(warnings)) return 0
  let n = 0
  for (const w of warnings) {
    if (typeof w === "string" && /error\s*analysis|error-analysis|slice\s*severity/i.test(w)) n += 1
  }
  return n
}

export type DashboardMlFactoryRollup = {
  available: boolean
  partial: boolean
  activeModelCount: number | null
  approvedDeploymentCandidateCount: number | null
  modelsRequiringReviewHint: number | null
  failedEvaluationsCount: number | null
  openDeploymentCandidatesCount: number | null
  errorAnalysisWarningsHint: number | null
  driftWarningsHint: number | null
}

export async function fetchDashboardMlFactoryRollup(): Promise<DashboardMlFactoryRollup> {
  const empty: DashboardMlFactoryRollup = {
    available: false,
    partial: false,
    activeModelCount: null,
    approvedDeploymentCandidateCount: null,
    modelsRequiringReviewHint: null,
    failedEvaluationsCount: null,
    openDeploymentCandidatesCount: null,
    errorAnalysisWarningsHint: null,
    driftWarningsHint: null,
  }

  let health: unknown
  try {
    health = await apiFetch<unknown>("/ml/model-health", { method: "GET" })
  } catch {
    return empty
  }

  if (!isRecord(health)) {
    return empty
  }

  const activeModelCount = readTopLevelInt(health, ["active_model_count", "activeModelCount"])
  const approvedDeploymentCandidateCount = readTopLevelInt(health, [
    "approved_deployment_candidate_count",
    "approvedDeploymentCandidateCount",
  ])

  const metaModelsReview = readMetadataInt(health, [
    "models_requiring_review",
    "pending_review_count",
    "models_pending_review",
    "n_models_requiring_review",
  ])

  const metaErrAnalysis = readMetadataInt(health, [
    "open_error_analysis_items",
    "error_analysis_open_count",
    "open_error_analysis_count",
    "n_open_error_analysis",
  ])

  const metaDrift = readMetadataInt(health, [
    "open_drift_alerts",
    "dataset_drift_warnings",
    "model_drift_warnings",
    "drift_warning_count",
  ])

  const warnList = health.warnings
  const warnDrift = countDriftHintFromWarnings(warnList)
  const warnErr = countErrorAnalysisHintFromWarnings(warnList)

  const driftWarningsHint =
    metaDrift != null ? metaDrift : warnDrift > 0 ? warnDrift : null
  const errorAnalysisWarningsHint =
    metaErrAnalysis != null ? metaErrAnalysis : warnErr > 0 ? warnErr : null

  let deployRows: Record<string, unknown>[] = []
  let evalRows: Record<string, unknown>[] = []
  let deployOk = false
  let evalOk = false

  try {
    const d = await apiFetch<unknown>("/ml/deployment-candidates?limit=500", { method: "GET" })
    deployRows = asRecordArray(d)
    deployOk = true
  } catch {
    /* list unavailable */
  }

  try {
    const e = await apiFetch<unknown>("/ml/evaluation-runs?limit=500", { method: "GET" })
    evalRows = asRecordArray(e)
    evalOk = true
  } catch {
    /* list unavailable */
  }

  const openDeploy = deployOk ? countOpenDeploymentCandidates(deployRows) : null
  const failedEval = evalOk ? countFailedEvaluations(evalRows) : null

  const modelsRequiringReviewHint =
    metaModelsReview != null ? metaModelsReview : openDeploy != null ? openDeploy : null

  return {
    available: true,
    partial: !deployOk || !evalOk,
    activeModelCount,
    approvedDeploymentCandidateCount,
    modelsRequiringReviewHint,
    failedEvaluationsCount: failedEval,
    openDeploymentCandidatesCount: openDeploy,
    errorAnalysisWarningsHint,
    driftWarningsHint,
  }
}
