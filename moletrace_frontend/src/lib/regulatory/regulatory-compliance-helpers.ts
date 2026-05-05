import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"

export function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

export function asArray(data: unknown): unknown[] {
  if (Array.isArray(data)) return data
  if (data && typeof data === "object") {
    const o = data as Record<string, unknown>
    if (Array.isArray(o.items)) return o.items
    if (Array.isArray(o.results)) return o.results
  }
  return []
}

const OPEN_ACTION = new Set(["open", "in_progress", "deferred"])

export function isOpenRegulatoryAction(row: Record<string, unknown>): boolean {
  return OPEN_ACTION.has(readRecordString(row, "status") ?? "")
}

export function findDossierBySpectraCheckSessionId(
  dossiers: Record<string, unknown>[],
  sessionNumeric: number
): Record<string, unknown> | null {
  for (const d of dossiers) {
    const sid = readRecordNumber(d, "spectracheck_session_id")
    if (sid != null && sid === sessionNumeric) return d
  }
  return null
}

export function parseSessionIdToNumber(sessionId: string | null | undefined): number | null {
  if (!sessionId?.trim()) return null
  const n = Number.parseInt(sessionId.trim(), 10)
  if (!Number.isFinite(n) || n < 1) return null
  return n
}

export function labelStatus(raw: string | undefined): string {
  if (!raw) return "—"
  return raw.replace(/_/g, " ")
}
