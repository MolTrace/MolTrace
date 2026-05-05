import { apiFetch, ApiError } from "@/lib/api/client"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"

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

function requirementStatus(row: Record<string, unknown>): string {
  return readRecordString(row, "status") ?? ""
}

async function mapInChunks<T, R>(items: T[], size: number, fn: (item: T) => Promise<R>): Promise<R[]> {
  const out: R[] = []
  for (let i = 0; i < items.length; i += size) {
    const chunk = items.slice(i, i + size)
    out.push(...(await Promise.all(chunk.map(fn))))
  }
  return out
}

export type DashboardRegulatorySummary =
  | {
      available: true
      activeDossiers: number
      inReview: number
      reqsNeedEvidence: number
      highRisk: number
    }
  | { available: false }

/**
 * GET /regulatory/dossiers plus lightweight per-dossier requirement and risk GETs
 * (same derivation as Regulatory Intelligence landing summaries).
 */
export async function fetchDashboardRegulatorySummary(): Promise<DashboardRegulatorySummary> {
  try {
    const raw = await apiFetch<unknown>("/regulatory/dossiers", { method: "GET" })
    const dossiers = asArray(raw).filter(isRecord) as Record<string, unknown>[]
    const activeDossiers = dossiers.filter((d) => readRecordString(d, "status") !== "archived").length
    const inReview = dossiers.filter((d) => readRecordString(d, "status") === "in_review").length

    const enriched = await mapInChunks(dossiers, 4, async (row) => {
      const did = readRecordNumber(row, "id")
      if (did == null) return { missingEvidenceCount: 0, risk: undefined as string | undefined }
      let missingEvidenceCount = 0
      try {
        const reqRaw = await apiFetch<unknown>(`/regulatory/dossiers/${did}/requirements`, { method: "GET" })
        const reqs = asArray(reqRaw).filter(isRecord) as Record<string, unknown>[]
        missingEvidenceCount = reqs.filter((r) => requirementStatus(r) === "evidence_needed").length
      } catch {
        /* keep zero */
      }
      let risk: string | undefined
      try {
        const r = await apiFetch<Record<string, unknown>>(`/regulatory/dossiers/${did}/risk-assessment`, {
          method: "GET",
        })
        risk = readRecordString(r, "overall_risk") ?? undefined
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 404)) {
          /* ignore */
        }
      }
      return { missingEvidenceCount, risk }
    })

    let reqsNeedEvidence = 0
    let highRisk = 0
    for (const e of enriched) {
      reqsNeedEvidence += e.missingEvidenceCount
      const rl = e.risk?.toLowerCase()
      if (rl === "high" || rl === "critical") highRisk += 1
    }

    return {
      available: true,
      activeDossiers,
      inReview,
      reqsNeedEvidence,
      highRisk,
    }
  } catch {
    return { available: false }
  }
}
