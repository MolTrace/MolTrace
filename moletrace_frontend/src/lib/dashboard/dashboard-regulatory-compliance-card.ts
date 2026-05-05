import { apiFetch } from "@/lib/api/client"
import { readRecordString } from "@/components/projects/project-workspace-utils"
import { asArray, isOpenRegulatoryAction, isRecord } from "@/src/lib/regulatory/regulatory-compliance-helpers"

export type RegulatoryComplianceCardData =
  | {
      available: true
      openActionItems: number
      criticalActionItems: number
      blockedDossiers: number
      qNmrGaps: number
      nitrosamineReviewItems: number
    }
  | { available: false }

/**
 * GET /regulatory/dossiers and GET /regulatory/action-items only.
 * qNMR / nitrosamine lines use open action item rows with matching action_type (source-linked triage, not legal claims).
 */
export async function fetchRegulatoryComplianceCardData(): Promise<RegulatoryComplianceCardData> {
  try {
    const [dRaw, aRaw] = await Promise.all([
      apiFetch<unknown>("/regulatory/dossiers?limit=500", { method: "GET" }),
      apiFetch<unknown>("/regulatory/action-items?limit=500", { method: "GET" }),
    ])
    const dossiers = asArray(dRaw).filter(isRecord) as Record<string, unknown>[]
    const actions = asArray(aRaw).filter(isRecord) as Record<string, unknown>[]
    const openRows = actions.filter(isOpenRegulatoryAction)
    const criticalActionItems = openRows.filter((a) => readRecordString(a, "severity") === "critical").length
    const blockedDossiers = dossiers.filter((d) => readRecordString(d, "status") === "blocked").length
    const qNmrGaps = openRows.filter((a) => readRecordString(a, "action_type") === "qnmr_validation_gap").length
    const nitrosamineReviewItems = openRows.filter(
      (a) => readRecordString(a, "action_type") === "nitrosamine_risk_review"
    ).length
    return {
      available: true,
      openActionItems: openRows.length,
      criticalActionItems,
      blockedDossiers,
      qNmrGaps,
      nitrosamineReviewItems,
    }
  } catch {
    return { available: false }
  }
}
