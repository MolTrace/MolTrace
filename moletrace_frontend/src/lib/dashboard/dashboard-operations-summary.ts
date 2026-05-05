import { apiFetch } from "@/lib/api/client"
import { countOpenDrift, extractDriftRows } from "./dashboard-method-health"

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null
}

function readStr(target: unknown, keys: string[]): string | null {
  const obj = isRecord(target) ? target : null
  if (!obj) return null
  for (const key of keys) {
    const value = obj[key]
    if (typeof value === "string" && value.trim()) return value.trim()
  }
  return null
}

function readNum(target: unknown, keys: string[]): number | null {
  const obj = isRecord(target) ? target : null
  if (!obj) return null
  for (const key of keys) {
    const value = obj[key]
    if (typeof value === "number" && Number.isFinite(value)) return value
  }
  return null
}

function sumActiveAnalysisJobs(counts: Record<string, unknown>): number {
  const activeKeys = ["queued", "running", "in_progress", "pending", "claimed", "starting"]
  let total = 0
  for (const key of activeKeys) {
    const v = counts[key]
    if (typeof v === "number" && Number.isFinite(v)) total += v
  }
  return total
}

export type DashboardOperationsRollup = {
  available: boolean
  partial: boolean
  systemHealthStatus: string | null
  activeJobs: number | null
  failedJobs: number | null
  securityWarnings: number | null
  openDriftAlerts: number | null
}

export async function fetchDashboardOperationsSummary(): Promise<DashboardOperationsRollup | null> {
  let okHealth = false
  let okJobs = false
  let okSecurity = false
  let okDrift = false

  let healthJson: unknown = null
  let jobsJson: unknown = null
  let securityJson: unknown = null
  let driftJson: unknown = null

  try {
    healthJson = await apiFetch<unknown>("/system/health", { method: "GET" })
    okHealth = true
  } catch {
    /* ignore */
  }

  try {
    jobsJson = await apiFetch<unknown>("/system/jobs/summary", { method: "GET" })
    okJobs = true
  } catch {
    /* ignore */
  }

  try {
    securityJson = await apiFetch<unknown>("/security/summary", { method: "GET" })
    okSecurity = true
  } catch {
    /* ignore */
  }

  try {
    driftJson = await apiFetch<unknown>("/model-health/drift-alerts", { method: "GET" })
    okDrift = true
  } catch {
    /* ignore */
  }

  const okCount = [okHealth, okJobs, okSecurity, okDrift].filter(Boolean).length
  const available = okCount > 0
  const partial = available && okCount < 4

  if (!available) {
    return null
  }

  const healthStatus = okHealth
    ? readStr(healthJson, ["status", "overall_status", "state"])
    : null

  let activeJobs: number | null = null
  let failedJobs: number | null = null
  if (okJobs && isRecord(jobsJson)) {
    const analysisCounts = jobsJson["analysis_job_status_counts"]
    if (isRecord(analysisCounts)) {
      activeJobs = sumActiveAnalysisJobs(analysisCounts)
      const failed = analysisCounts["failed"]
      failedJobs = typeof failed === "number" && Number.isFinite(failed) ? failed : null
    }
  }

  const securityWarnings = okSecurity
    ? readNum(securityJson, ["open_warnings", "warning_count", "warnings"])
    : null

  const driftRows = okDrift ? extractDriftRows(driftJson) : []
  const openDriftAlerts = okDrift ? countOpenDrift(driftRows) : null

  return {
    available,
    partial,
    systemHealthStatus: healthStatus,
    activeJobs,
    failedJobs,
    securityWarnings,
    openDriftAlerts,
  }
}
