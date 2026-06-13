import { apiFetch } from "@/lib/api/client"

type Row = Record<string, unknown>

export type DashboardCoreModuleKey = "spectracheck" | "regulatory_hub" | "reactioniq"

export type DashboardCoreModuleActivityRow = {
  module: DashboardCoreModuleKey
  label: string
  count: number
  latestAt: string | null
}

export type DashboardCoreModuleActivity = {
  available: boolean
  total: number
  rows: DashboardCoreModuleActivityRow[]
  warnings: string[]
}

const MODULE_ORDER: DashboardCoreModuleKey[] = ["spectracheck", "regulatory_hub", "reactioniq"]

const MODULE_LABELS: Record<DashboardCoreModuleKey, string> = {
  spectracheck: "SpectraCheck",
  regulatory_hub: "ComplianceCore",
  reactioniq: "ReactionIQ",
}

const MODULE_ALIASES: Record<string, DashboardCoreModuleKey> = {
  spectracheck: "spectracheck",
  spectroscopy: "spectracheck",
  nmr: "spectracheck",
  regulatory: "regulatory_hub",
  regulatory_hub: "regulatory_hub",
  regulatoryhub: "regulatory_hub",
  reaction: "reactioniq",
  reactions: "reactioniq",
  reaction_optimization: "reactioniq",
  reactioniq: "reactioniq",
}

function emptyActivity(available = false, warnings: string[] = []): DashboardCoreModuleActivity {
  return {
    available,
    total: 0,
    rows: MODULE_ORDER.map((module) => ({
      module,
      label: MODULE_LABELS[module],
      count: 0,
      latestAt: null,
    })),
    warnings,
  }
}

function isRecord(v: unknown): v is Row {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function asRows(payload: unknown): Row[] {
  if (Array.isArray(payload)) return payload.filter(isRecord)
  if (isRecord(payload) && Array.isArray(payload.items)) return payload.items.filter(isRecord)
  return []
}

function readRecord(v: unknown): Row | null {
  return isRecord(v) ? v : null
}

function readStr(v: unknown): string {
  if (typeof v === "string" && v.trim()) return v.trim()
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  return ""
}

function normalizeModule(raw: unknown): DashboardCoreModuleKey | null {
  const token = readStr(raw)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
  if (!token) return null
  return MODULE_ALIASES[token] ?? null
}

function readMetadata(row: Row): Row {
  return readRecord(row.metadata_json) ?? readRecord(row.metadata) ?? {}
}

function readCreatedAt(row: Row): string | null {
  const value =
    readStr(row.created_at) ||
    readStr(row.createdAt) ||
    readStr(row.timestamp) ||
    readStr(row.updated_at) ||
    readStr(row.updatedAt)
  return value || null
}

function latestTimestamp(current: string | null, candidate: string | null): string | null {
  if (!candidate) return current
  if (!current) return candidate
  const currentMs = Date.parse(current)
  const candidateMs = Date.parse(candidate)
  if (!Number.isFinite(candidateMs)) return current
  if (!Number.isFinite(currentMs)) return candidate
  return candidateMs > currentMs ? candidate : current
}

export async function fetchDashboardCoreModuleActivity(): Promise<DashboardCoreModuleActivity> {
  let rows: Row[]
  try {
    rows = asRows(
      await apiFetch<unknown>("/analytics/events?event_type=core_module_opened&limit=200", {
        method: "GET",
      }),
    )
  } catch {
    return emptyActivity(false, ["Core module analytics unavailable."])
  }

  const counts: Record<DashboardCoreModuleKey, { count: number; latestAt: string | null }> = {
    spectracheck: { count: 0, latestAt: null },
    regulatory_hub: { count: 0, latestAt: null },
    reactioniq: { count: 0, latestAt: null },
  }

  for (const row of rows) {
    const metadata = readMetadata(row)
    const module = normalizeModule(metadata.module) ?? normalizeModule(row.module) ?? normalizeModule(row.event_module)
    if (!module) continue
    counts[module].count += 1
    counts[module].latestAt = latestTimestamp(counts[module].latestAt, readCreatedAt(row))
  }

  const activityRows = MODULE_ORDER.map((module) => ({
    module,
    label: MODULE_LABELS[module],
    count: counts[module].count,
    latestAt: counts[module].latestAt,
  }))

  return {
    available: true,
    total: activityRows.reduce((sum, row) => sum + row.count, 0),
    rows: activityRows,
    warnings: [],
  }
}
