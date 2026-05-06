import { apiFetch } from "@/lib/api/client"

type Row = Record<string, unknown>

function isRecord(v: unknown): v is Row {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readNum(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return Math.floor(v)
  if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Math.floor(Number(v))
  return null
}

function readStr(v: unknown): string {
  if (typeof v === "string" && v.trim()) return v.trim()
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  return ""
}

function readList(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.map(readStr).filter(Boolean)
}

function readCount(rec: Row | null, keys: string[]): number | null {
  if (!rec) return null
  for (const key of keys) {
    const n = readNum(rec[key])
    if (n != null) return n
  }
  return null
}

function pickRecord(raw: unknown): Row | null {
  if (isRecord(raw)) return raw
  if (Array.isArray(raw)) {
    const first = raw.find(isRecord)
    return first ?? null
  }
  return null
}

function asRecord(v: unknown): Row | null {
  return isRecord(v) ? v : null
}

function asActionItems(v: unknown): Row[] {
  if (Array.isArray(v)) return v.filter(isRecord) as Row[]
  if (!isRecord(v)) return []
  const items = v.items
  if (Array.isArray(items)) return items.filter(isRecord) as Row[]
  return []
}

function countOpenBlockers(rows: Row[]): number {
  let n = 0
  for (const row of rows) {
    const status = readStr(row.status).toLowerCase()
    const severity = readStr(row.severity).toLowerCase()
    if (status === "blocked" || (status === "open" && (severity === "high" || severity === "critical"))) n += 1
  }
  return n
}

export type DashboardCrossModuleCommandCenter = {
  available: boolean
  partial: boolean
  sourceEndpoint: string
  spectracheckSummary: Row | null
  regulatorySummary: Row | null
  reactionSummary: Row | null
  latestSpectraCheckEvidenceStatus: string | null
  linkedRegulatoryActionItems: number | null
  openRegulatoryBlockers: number | null
  reactionConstraintsCreated: number | null
  optimizationRecommendationsAffectedByCompliance: number | null
  openCrossModuleActionItems: number | null
  warnings: string[]
  nextRecommendedAction: string | null
}

const EMPTY: DashboardCrossModuleCommandCenter = {
  available: false,
  partial: false,
  sourceEndpoint: "/cross-module/command-center",
  spectracheckSummary: null,
  regulatorySummary: null,
  reactionSummary: null,
  latestSpectraCheckEvidenceStatus: null,
  linkedRegulatoryActionItems: null,
  openRegulatoryBlockers: null,
  reactionConstraintsCreated: null,
  optimizationRecommendationsAffectedByCompliance: null,
  openCrossModuleActionItems: null,
  warnings: [],
  nextRecommendedAction: null,
}

export async function fetchDashboardCrossModuleCommandCenter(args?: {
  projectId?: number | null
  compoundId?: number | null
  batchId?: number | null
}): Promise<DashboardCrossModuleCommandCenter> {
  const endpoints = ["/cross-module/command-center"]
  if (args?.projectId != null) endpoints.unshift(`/cross-module/command-center/project/${args.projectId}`)
  if (args?.compoundId != null) endpoints.unshift(`/cross-module/command-center/compound/${args.compoundId}`)
  if (args?.batchId != null) endpoints.unshift(`/cross-module/command-center/batch/${args.batchId}`)

  let raw: unknown = null
  let sourceEndpoint = "/cross-module/command-center"
  for (const ep of endpoints) {
    try {
      raw = await apiFetch<unknown>(ep, { method: "GET" })
      sourceEndpoint = ep
      break
    } catch {
      /* try next scope */
    }
  }
  const root = pickRecord(raw)
  if (!root) return EMPTY

  const spectracheckSummary = asRecord(root.spectracheck_summary_json)
  const regulatorySummary = asRecord(root.regulatory_summary_json)
  const reactionSummary = asRecord(root.reaction_summary_json)
  const actionItems = asActionItems(root.open_cross_module_actions_json)

  const latestSpectraCheckEvidenceStatus =
    readStr(spectracheckSummary?.latest_evidence_status) ||
    readStr(spectracheckSummary?.evidence_status) ||
    readStr(spectracheckSummary?.status) ||
    null

  const linkedRegulatoryActionItems =
    readCount(regulatorySummary, ["linked_regulatory_action_items", "linked_action_items", "action_items_linked"]) ??
    readCount(root, ["linked_regulatory_action_items"])

  const openRegulatoryBlockers =
    readCount(regulatorySummary, ["open_regulatory_blockers", "regulatory_blockers_open", "open_blockers"]) ??
    countOpenBlockers(actionItems)

  const reactionConstraintsCreated =
    readCount(reactionSummary, ["reaction_constraints_created", "constraints_created"]) ??
    readCount(root, ["reaction_constraints_created"])

  const optimizationRecommendationsAffectedByCompliance =
    readCount(reactionSummary, [
      "optimization_recommendations_affected_by_compliance",
      "recommendations_affected_by_compliance",
      "compliance_affected_recommendations",
    ]) ?? readCount(root, ["optimization_recommendations_affected_by_compliance"])

  const openCrossModuleActionItems =
    readCount(root, ["open_cross_module_action_items_count", "open_action_items_count"]) ?? actionItems.length

  const warnings = [...readList(root.warnings), ...readList(root.warnings_json)]
  const nextRecommendedAction =
    readStr(root.next_recommended_action) ||
    readStr(root.next_action) ||
    readStr(root.recommended_next_action) ||
    null

  return {
    available: true,
    partial: false,
    sourceEndpoint,
    spectracheckSummary,
    regulatorySummary,
    reactionSummary,
    latestSpectraCheckEvidenceStatus,
    linkedRegulatoryActionItems,
    openRegulatoryBlockers,
    reactionConstraintsCreated,
    optimizationRecommendationsAffectedByCompliance,
    openCrossModuleActionItems,
    warnings,
    nextRecommendedAction,
  }
}
