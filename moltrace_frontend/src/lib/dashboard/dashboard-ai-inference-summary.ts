import { apiFetch } from "@/lib/api/client"

type Row = Record<string, unknown>

function isRecord(v: unknown): v is Row {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readNumLoose(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return Math.floor(v)
  if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Math.floor(Number(v))
  return null
}

function readTopLevelInt(raw: unknown, keys: string[]): number | null {
  if (!isRecord(raw)) return null
  for (const key of keys) {
    const n = readNumLoose(raw[key])
    if (n != null && n >= 0) return n
  }
  return null
}

function asRecordArray(data: unknown): Row[] {
  if (Array.isArray(data)) return data.filter(isRecord) as Row[]
  if (!isRecord(data)) return []
  for (const key of ["items", "results", "rows", "data", "predictions", "services", "candidates", "active_learning_candidates"]) {
    const v = data[key]
    if (Array.isArray(v)) return v.filter(isRecord) as Row[]
  }
  return []
}

function countPredictionsRequiringReview(rows: Row[]): number {
  let n = 0
  for (const r of rows) {
    const status = String(r.status ?? r.review_status ?? "")
      .trim()
      .toLowerCase()
    const reviewReq = String(r.human_review_required ?? r.review_required ?? "")
      .trim()
      .toLowerCase()
    if (status.includes("review") || status.includes("pending") || reviewReq === "true") n += 1
  }
  return n
}

function countLowConfidence(rows: Row[]): number {
  let n = 0
  for (const r of rows) {
    const v = readNumLoose(r.confidence ?? r.confidence_score)
    if (v != null && v < 1) {
      if (v < 0.5) n += 1
      continue
    }
    if (v != null && v <= 50) n += 1
  }
  return n
}

function countOod(rows: Row[]): number {
  let n = 0
  for (const r of rows) {
    const ood = String(r.ood_status ?? r.is_ood ?? r.out_of_domain ?? "")
      .trim()
      .toLowerCase()
    if (ood === "true" || ood === "ood" || ood === "out_of_domain" || ood === "1") n += 1
  }
  return n
}

function countServiceFailures(rows: Row[]): number {
  let n = 0
  for (const r of rows) {
    const st = String(r.status ?? r.service_status ?? "")
      .trim()
      .toLowerCase()
    if (st.includes("fail") || st.includes("error") || st === "unhealthy" || st === "degraded") n += 1
  }
  return n
}

export type DashboardAiInferenceSummary = {
  available: boolean
  partial: boolean
  activeAiServices: number | null
  predictionsRequiringReview: number | null
  lowConfidencePredictions: number | null
  oodPredictions: number | null
  activeLearningCandidates: number | null
  serviceFailures: number | null
}

export async function fetchDashboardAiInferenceSummary(): Promise<DashboardAiInferenceSummary> {
  const empty: DashboardAiInferenceSummary = {
    available: false,
    partial: false,
    activeAiServices: null,
    predictionsRequiringReview: null,
    lowConfidencePredictions: null,
    oodPredictions: null,
    activeLearningCandidates: null,
    serviceFailures: null,
  }

  let monitoring: unknown
  try {
    monitoring = await apiFetch<unknown>("/ai/model-monitoring", { method: "GET" })
  } catch {
    return empty
  }
  if (!isRecord(monitoring)) return empty

  let predictionsOk = false
  let servicesOk = false
  let candidatesOk = false
  let predictionRows: Row[] = []
  let serviceRows: Row[] = []
  let candidateRows: Row[] = []

  try {
    predictionRows = asRecordArray(await apiFetch<unknown>("/ai/predictions", { method: "GET" }))
    predictionsOk = true
  } catch {
    /* list unavailable */
  }

  try {
    serviceRows = asRecordArray(await apiFetch<unknown>("/ai/services", { method: "GET" }))
    servicesOk = true
  } catch {
    /* list unavailable */
  }

  try {
    candidateRows = asRecordArray(await apiFetch<unknown>("/ai/active-learning/candidates", { method: "GET" }))
    candidatesOk = true
  } catch {
    /* list unavailable */
  }

  const activeAiServices =
    readTopLevelInt(monitoring, ["active_services", "active_ai_services"]) ??
    (servicesOk ? serviceRows.filter((r) => String(r.status ?? "").toLowerCase() === "active").length : null)
  const predictionsRequiringReview =
    readTopLevelInt(monitoring, ["predictions_requiring_review", "review_required_count"]) ??
    (predictionsOk ? countPredictionsRequiringReview(predictionRows) : null)
  const lowConfidencePredictions =
    readTopLevelInt(monitoring, ["low_confidence_count", "low_confidence_predictions"]) ??
    (predictionsOk ? countLowConfidence(predictionRows) : null)
  const oodPredictions =
    readTopLevelInt(monitoring, ["ood_count", "ood_predictions"]) ?? (predictionsOk ? countOod(predictionRows) : null)
  const activeLearningCandidates =
    readTopLevelInt(monitoring, ["active_learning_candidates", "active_learning_count"]) ??
    (candidatesOk ? candidateRows.length : null)
  const serviceFailures =
    readTopLevelInt(monitoring, ["service_failure_count", "service_failures"]) ??
    (servicesOk ? countServiceFailures(serviceRows) : null)

  return {
    available: true,
    partial: !predictionsOk || !servicesOk || !candidatesOk,
    activeAiServices,
    predictionsRequiringReview,
    lowConfidencePredictions,
    oodPredictions,
    activeLearningCandidates,
    serviceFailures,
  }
}
