import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"

export const BATCH_ALIQUOT_TOOLTIP =
  "Batches and aliquots connect physical material to analytical evidence, reaction experiments, and regulatory dossiers."

export function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

export function normalizeBatchList(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord)
  if (isRecord(data)) {
    for (const k of ["batches", "items", "results", "data", "rows"]) {
      const v = data[k]
      if (Array.isArray(v)) return v.filter(isRecord)
    }
  }
  return []
}

export function normalizeAliquotList(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord)
  if (isRecord(data)) {
    for (const k of ["aliquots", "items", "results", "data", "rows"]) {
      const v = data[k]
      if (Array.isArray(v)) return v.filter(isRecord)
    }
  }
  return []
}

export function pickStr(row: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = readRecordString(row, k)
    if (v != null && String(v).trim() !== "") return String(v).trim()
  }
  return "—"
}

export function pickNum(row: Record<string, unknown>, keys: string[]): number | undefined {
  for (const k of keys) {
    const n = readRecordNumber(row, k)
    if (n != null && Number.isFinite(n)) return n
  }
  return undefined
}

export function formatBatchUpdated(row: Record<string, unknown>): string {
  const raw = pickStr(row, ["updated_at", "updatedAt", "modified_at", "modifiedAt"])
  if (raw === "—") return "—"
  const t = Date.parse(raw)
  if (!Number.isNaN(t)) return new Date(t).toLocaleString()
  return raw
}

export function readBatchId(row: Record<string, unknown>): string | null {
  const n = readRecordNumber(row, "id")
  if (n != null) return String(n)
  const s = readRecordString(row, "id")?.trim()
  return s || null
}

export function readRowCompoundId(row: Record<string, unknown>): string | null {
  const n = readRecordNumber(row, "compound_id") ?? readRecordNumber(row, "compoundId")
  if (n != null) return String(n)
  const s = readRecordString(row, "compound_id") ?? readRecordString(row, "compoundId")
  return s?.trim() || null
}

export function batchMatchesCompound(row: Record<string, unknown>, compoundId: string): boolean {
  const cid = readRowCompoundId(row)
  if (!cid || !compoundId.trim()) return false
  return String(cid) === String(compoundId.trim())
}

export function linkedSessionReactionDossier(row: Record<string, unknown>): string {
  const parts: string[] = []
  const sessNum =
    readRecordNumber(row, "spectracheck_session_id") ?? readRecordNumber(row, "spectracheckSessionId")
  const sessStr = readRecordString(row, "spectracheck_session_id") ?? readRecordString(row, "spectracheckSessionId")
  const sess = sessStr?.trim() || (sessNum != null ? String(sessNum) : "")
  const rxn =
    readRecordNumber(row, "reaction_experiment_id") ?? readRecordNumber(row, "reactionExperimentId") ?? null
  const dos =
    readRecordNumber(row, "regulatory_dossier_id") ?? readRecordNumber(row, "regulatoryDossierId") ?? null
  if (sess) parts.push(`session ${sess}`)
  if (rxn != null) parts.push(`reaction ${rxn}`)
  if (dos != null) parts.push(`dossier ${dos}`)
  return parts.length > 0 ? parts.join(" · ") : "—"
}
