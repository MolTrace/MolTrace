/**
 * Dashboard rollup from GET /model-health and GET /model-health/drift-alerts (global, no session fan-out).
 */

import { apiFetch } from "@/lib/api/client"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(o: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "string" && v.trim()) return v.trim()
    if (typeof v === "number" && Number.isFinite(v)) return String(v)
  }
  return ""
}

function parseDeprecatedFromMethodsList(items: Record<string, unknown>[]): number {
  let n = 0
  for (const item of items) {
    const st = readStr(item, ["status", "lifecycle", "tier", "phase"]).toLowerCase()
    const dep =
      readStr(item, ["deprecated", "is_deprecated", "isDeprecated"]).toLowerCase() === "true" ||
      st.includes("deprecated") ||
      st.includes("retired")
    if (dep) n += 1
  }
  return n
}

function readDeprecatedCount(raw: unknown): number | null {
  if (raw == null) return null
  if (!isRecord(raw)) return null
  const dc =
    typeof raw.deprecated_method_count === "number"
      ? raw.deprecated_method_count
      : typeof raw.deprecatedMethods === "number"
        ? raw.deprecatedMethods
        : null
  if (dc != null && Number.isFinite(dc)) return Math.max(0, Math.floor(dc))
  const ds = readStr(raw, ["deprecated_methods", "deprecatedMethods", "deprecated_count", "retired_count"])
  if (ds && Number.isFinite(Number(ds))) return Math.max(0, Math.floor(Number(ds)))
  const nested = raw.methods ?? raw.items
  if (Array.isArray(nested)) {
    const rows = nested.filter(isRecord) as Record<string, unknown>[]
    return rows.length ? parseDeprecatedFromMethodsList(rows) : 0
  }
  return null
}

/** Mirrors validation dashboard parsing for active / experimental. */
export function readModelHealthActiveExperimental(raw: unknown): {
  active: number | null
  experimental: number | null
} {
  if (raw == null) return { active: null, experimental: null }
  if (Array.isArray(raw)) {
    let active = 0
    let experimental = 0
    for (const item of raw) {
      if (!isRecord(item)) continue
      const role = readStr(item, ["lifecycle", "tier", "kind", "category", "phase"]).toLowerCase()
      const exp =
        readStr(item, ["experimental", "is_experimental", "isExperimental"]).toLowerCase() === "true" ||
        role.includes("experimental")
      if (exp) experimental += 1
      else active += 1
    }
    return { active: raw.length ? active : 0, experimental: raw.length ? experimental : 0 }
  }
  if (!isRecord(raw)) return { active: null, experimental: null }
  const an = readStr(raw, ["active_methods", "activeMethods", "active_method_count", "active_count"])
  const en = readStr(raw, ["experimental_methods", "experimentalMethods", "experimental_count"])
  const ac =
    typeof raw.active_method_count === "number"
      ? raw.active_method_count
      : typeof raw.activeMethods === "number"
        ? raw.activeMethods
        : an
          ? Number(an)
          : null
  const ec =
    typeof raw.experimental_method_count === "number"
      ? raw.experimental_method_count
      : typeof raw.experimentalMethods === "number"
        ? raw.experimentalMethods
        : en
          ? Number(en)
          : null
  const activeNum = ac != null && Number.isFinite(ac) ? Math.max(0, Math.floor(ac)) : null
  const expNum = ec != null && Number.isFinite(ec) ? Math.max(0, Math.floor(ec)) : null
  if (activeNum != null || expNum != null) return { active: activeNum, experimental: expNum }
  const nested = raw.methods ?? raw.items
  if (Array.isArray(nested)) return readModelHealthActiveExperimental(nested)
  return { active: null, experimental: null }
}

export function extractDriftRows(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord) as Record<string, unknown>[]
  if (!isRecord(data)) return []
  for (const k of ["drift_alerts", "alerts", "items", "results", "rows"]) {
    const v = data[k]
    if (Array.isArray(v)) return v.filter(isRecord) as Record<string, unknown>[]
  }
  return []
}

export function countOpenDrift(rows: Record<string, unknown>[]): number {
  const terminal = new Set(["resolved", "closed", "dismissed"])
  return rows.filter((r) => {
    const st = readStr(r, ["status", "alert_status", "state"]).toLowerCase()
    if (!st) return true
    return !terminal.has(st)
  }).length
}

export function pickLatestValidationRunStatusFromHealth(raw: unknown): string | null {
  if (!isRecord(raw)) return null
  const direct =
    readStr(raw, [
      "latest_validation_run_status",
      "latest_validation_status",
      "last_validation_run_status",
      "last_validation_status",
    ]) || ""
  if (direct) return direct
  const nested = raw.latest_validation_run ?? raw.last_validation_run ?? raw.latest_validation
  if (isRecord(nested)) {
    const st = readStr(nested, ["status", "state", "validation_status", "run_status"])
    if (st) return st
  }
  const summary = raw.validation_summary
  if (isRecord(summary)) {
    const st = readStr(summary, ["latest_status", "status", "overall_status"])
    if (st) return st
  }
  return null
}

export type DashboardMethodHealthRollup = {
  /** True if at least one of the two endpoints returned successfully. */
  available: boolean
  /** True if one endpoint failed while the other succeeded. */
  partial: boolean
  activeMethods: number | null
  experimentalMethods: number | null
  deprecatedMethods: number | null
  openDriftAlerts: number | null
  latestValidationRunStatus: string | null
}

export async function fetchDashboardMethodHealthAggregate(): Promise<DashboardMethodHealthRollup> {
  let healthOk = false
  let driftOk = false
  let healthRaw: unknown = null
  let driftRaw: unknown = null

  try {
    healthRaw = await apiFetch<unknown>("/model-health", { method: "GET" })
    healthOk = true
  } catch {
    /* partial handled below */
  }
  try {
    driftRaw = await apiFetch<unknown>("/model-health/drift-alerts", { method: "GET" })
    driftOk = true
  } catch {
    /* partial */
  }

  const partial = (healthOk && !driftOk) || (!healthOk && driftOk)

  const ae = healthOk ? readModelHealthActiveExperimental(healthRaw) : { active: null, experimental: null }
  const dep = healthOk ? readDeprecatedCount(healthRaw) : null
  const driftRows = driftOk ? extractDriftRows(driftRaw) : []
  const openDrift = driftOk ? countOpenDrift(driftRows) : null
  const latestVal = healthOk ? pickLatestValidationRunStatusFromHealth(healthRaw) : null

  const available = healthOk || driftOk

  return {
    available,
    partial,
    activeMethods: ae.active,
    experimentalMethods: ae.experimental,
    deprecatedMethods: dep,
    openDriftAlerts: openDrift,
    latestValidationRunStatus: latestVal,
  }
}
