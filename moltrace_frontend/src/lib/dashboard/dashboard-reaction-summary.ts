import { apiFetch } from "@/lib/api/client"

/**
 * GET /reaction-projects — compact counts for the dashboard's Repho section.
 *
 * Deliberately a plain roll-up of the project list rather than anything derived: the dashboard's
 * job here is to tell a chemist what is in flight and give them a way back in, not to restate
 * optimization results out of context.
 */

type Row = Record<string, unknown>

function isRecord(v: unknown): v is Row {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function normalizeProjectList(data: unknown): Row[] {
  if (Array.isArray(data)) return data.filter(isRecord)
  if (isRecord(data)) {
    for (const k of ["reaction_projects", "projects", "items", "results", "data", "rows"]) {
      const v = data[k]
      if (Array.isArray(v)) return v.filter(isRecord)
    }
  }
  return []
}

function readStr(row: Row, key: string): string {
  const v = row[key]
  return typeof v === "string" ? v.trim() : ""
}

function statusNorm(row: Row): string {
  return readStr(row, "status").toLowerCase().replace(/\s+/g, "_")
}

/** Sortable timestamp, or null when the row carries nothing usable. */
function updatedAt(row: Row): number | null {
  for (const key of ["updated_at", "created_at"]) {
    const raw = readStr(row, key)
    if (!raw) continue
    const t = Date.parse(raw)
    if (Number.isFinite(t)) return t
  }
  return null
}

export type DashboardReactionSummary =
  | {
      available: true
      totalProjects: number
      activeProjects: number
      draftProjects: number
      completedProjects: number
      /** The most recently touched project, for a "pick up where you left off" link. */
      latestProjectId: number | null
      latestProjectName: string | null
    }
  | { available: false }

export async function fetchDashboardReactionSummary(): Promise<DashboardReactionSummary> {
  let rows: Row[]
  try {
    const raw = await apiFetch<unknown>("/reaction-projects?limit=200", { method: "GET" })
    rows = normalizeProjectList(raw)
  } catch {
    return { available: false }
  }

  // Archived projects are deliberately excluded from every count — they are not work in flight.
  const live = rows.filter((r) => statusNorm(r) !== "archived")

  let latest: Row | null = null
  let latestAt = -Infinity
  for (const row of live) {
    const t = updatedAt(row)
    if (t != null && t > latestAt) {
      latestAt = t
      latest = row
    }
  }
  // A list with no parseable timestamps still deserves a link in; fall back to the first row.
  if (latest == null && live.length > 0) latest = live[0]

  const latestId = latest && typeof latest.id === "number" && Number.isFinite(latest.id) ? latest.id : null
  const latestName = latest ? readStr(latest, "name") || null : null

  return {
    available: true,
    totalProjects: live.length,
    activeProjects: live.filter((r) => statusNorm(r) === "active").length,
    draftProjects: live.filter((r) => statusNorm(r) === "draft").length,
    completedProjects: live.filter((r) => statusNorm(r) === "completed").length,
    latestProjectId: latestId,
    latestProjectName: latestName,
  }
}
