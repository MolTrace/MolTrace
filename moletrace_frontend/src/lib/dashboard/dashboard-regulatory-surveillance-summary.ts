import { apiFetch } from "@/lib/api/client"
import { readRecordString } from "@/components/projects/project-workspace-utils"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function asArray(data: unknown): unknown[] {
  if (Array.isArray(data)) return data
  if (data && typeof data === "object") {
    const o = data as Record<string, unknown>
    if (Array.isArray(o.items)) return o.items
    if (Array.isArray(o.results)) return o.results
  }
  return []
}

function readIntList(row: Record<string, unknown>, key: string): number[] {
  const v = row[key]
  if (!Array.isArray(v)) return []
  return v.filter((x): x is number => typeof x === "number" && Number.isFinite(x))
}

export type DashboardRegulatorySurveillanceSummary =
  | {
      available: true
      /** Change rows where change_type is not no_change */
      changesDetected: number
      highImpactChanges: number
      dossiersAffected: number
      pendingRuleUpdateProposals: number
      unreadRegulatoryNotifications: number
    }
  | { available: false }

/**
 * GET /regulatory/changes, GET /regulatory/notifications, GET /regulatory/rule-update-proposals
 * — same derivations as Regulatory Surveillance dashboard summary metrics.
 */
export async function fetchDashboardRegulatorySurveillanceSummary(): Promise<DashboardRegulatorySurveillanceSummary> {
  try {
    const [changesRaw, notificationsRaw, proposalsRaw] = await Promise.all([
      apiFetch<unknown>("/regulatory/changes?limit=500", { method: "GET" }),
      apiFetch<unknown>("/regulatory/notifications?limit=200", { method: "GET" }),
      apiFetch<unknown>("/regulatory/rule-update-proposals?limit=500&status=proposed", { method: "GET" }),
    ])

    const changes = asArray(changesRaw).filter(isRecord) as Record<string, unknown>[]
    const notifications = asArray(notificationsRaw).filter(isRecord) as Record<string, unknown>[]
    const proposals = asArray(proposalsRaw).filter(isRecord) as Record<string, unknown>[]

    const changesDetected = changes.filter((r) => readRecordString(r, "change_type") !== "no_change").length
    const highImpactChanges = changes.filter((r) => {
      const s = readRecordString(r, "severity")
      return s === "high" || s === "critical"
    }).length

    const dossierIds = new Set<number>()
    for (const r of changes) {
      for (const id of readIntList(r, "affected_dossier_ids_json")) {
        dossierIds.add(id)
      }
    }

    const unreadRegulatoryNotifications = notifications.filter(
      (r) => readRecordString(r, "status") === "unread",
    ).length

    return {
      available: true,
      changesDetected,
      highImpactChanges,
      dossiersAffected: dossierIds.size,
      pendingRuleUpdateProposals: proposals.length,
      unreadRegulatoryNotifications,
    }
  } catch {
    return { available: false }
  }
}
