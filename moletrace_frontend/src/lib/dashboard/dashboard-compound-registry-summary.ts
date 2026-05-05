import { apiFetch } from "@/lib/api/client"
import { normalizeBatchList } from "@/components/batches/batch-registry-utils"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function normalizeCompoundsList(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord)
  if (isRecord(data)) {
    for (const k of ["compounds", "items", "results", "data", "rows"]) {
      const v = data[k]
      if (Array.isArray(v)) return v.filter(isRecord)
    }
  }
  return []
}

function pickNum(row: Record<string, unknown>, keys: string[]): number | undefined {
  for (const k of keys) {
    const n = readRecordNumber(row, k)
    if (n != null && Number.isFinite(n)) return n
  }
  return undefined
}

function compoundStatusNorm(row: Record<string, unknown>): string {
  return (readRecordString(row, "status") ?? "").trim().toLowerCase().replace(/\s+/g, "_")
}

function rowNeedsReview(row: Record<string, unknown>): boolean {
  const s = compoundStatusNorm(row)
  if (s === "needs_review") return true
  if (
    s.includes("needs_review") ||
    s.includes("review_required") ||
    s.includes("pending_review") ||
    s.includes("human_review")
  )
    return true
  const flag = row.requires_review ?? row.needs_review ?? row.needsReview
  if (flag === true) return true
  return false
}

function rowEvidenceLinked(row: Record<string, unknown>): boolean {
  const n =
    pickNum(row, ["evidence_link_count", "evidenceLinkCount", "linked_evidence_count", "linkedEvidenceCount"]) ?? 0
  if (n > 0) return true
  const b = row.evidence_linked ?? row.evidenceLinked
  return b === true || b === 1
}

function batchStatusNorm(row: Record<string, unknown>): string {
  return (readRecordString(row, "status") ?? "").trim().toLowerCase().replace(/\s+/g, "_")
}

export type DashboardCompoundRegistrySummary =
  | {
      available: true
      partial?: boolean
      activeCompounds: number
      activeBatches: number | null
      compoundsNeedingReview: number
      evidenceLinkedCompounds: number
    }
  | { available: false }

/**
 * GET /compound-registry/compounds and GET /compound-registry/batches — compact counts for the dashboard.
 */
export async function fetchDashboardCompoundRegistrySummary(): Promise<DashboardCompoundRegistrySummary> {
  let compounds: Record<string, unknown>[]
  try {
    const raw = await apiFetch<unknown>("/compound-registry/compounds", { method: "GET" })
    compounds = normalizeCompoundsList(raw)
  } catch {
    return { available: false }
  }

  let batches: Record<string, unknown>[] | null = null
  let batchesFailed = false
  try {
    const rawB = await apiFetch<unknown>("/compound-registry/batches", { method: "GET" })
    batches = normalizeBatchList(rawB)
  } catch {
    batchesFailed = true
  }

  const activeCompounds = compounds.filter((r) => compoundStatusNorm(r) === "active").length
  const compoundsNeedingReview = compounds.filter(rowNeedsReview).length
  const evidenceLinkedCompounds = compounds.filter(rowEvidenceLinked).length

  const activeBatches =
    !batchesFailed && batches != null ? batches.filter((r) => batchStatusNorm(r) === "active").length : null

  return {
    available: true,
    partial: batchesFailed,
    activeCompounds,
    activeBatches,
    compoundsNeedingReview,
    evidenceLinkedCompounds,
  }
}
