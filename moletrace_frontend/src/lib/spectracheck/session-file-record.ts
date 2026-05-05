/** Normalized row from GET /spectracheck/sessions/{id}/files or POST /files/upload */

export type SessionFileRecord = {
  file_id: string
  filename: string
  file_size: number | null
  sha256: string | null
  file_kind: string
  created_at: string | null
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(v: unknown): string | null {
  if (typeof v === "string") return v
  if (typeof v === "number") return String(v)
  return null
}

function readNum(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v
  if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Number(v)
  return null
}

export function normalizeSessionFileRecord(v: unknown): SessionFileRecord | null {
  if (!isRecord(v)) return null
  const file_id = readStr(v.file_id) ?? readStr(v.id) ?? readStr(v.fileId)
  if (!file_id) return null
  return {
    file_id,
    filename: readStr(v.filename) ?? readStr(v.name) ?? "—",
    file_size: readNum(v.file_size) ?? readNum(v.size),
    sha256: readStr(v.sha256) ?? readStr(v.file_sha256),
    file_kind: readStr(v.file_kind) ?? readStr(v.kind) ?? "other",
    created_at: readStr(v.created_at) ?? readStr(v.createdAt),
  }
}

export function normalizeSessionFileRecordList(data: unknown): SessionFileRecord[] {
  const src = Array.isArray(data)
    ? data
    : isRecord(data) && Array.isArray(data.files)
      ? data.files
      : isRecord(data) && Array.isArray(data.items)
        ? data.items
        : []
  const out: SessionFileRecord[] = []
  for (const item of src) {
    const f = normalizeSessionFileRecord(item)
    if (f) out.push(f)
  }
  return out
}
