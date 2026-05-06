import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"

export function projectsErrorMessage(err: unknown, fallback: string): string {
  return formatApiError(err, fallback)
}

export function readRecordString(obj: unknown, key: string): string | undefined {
  if (!obj || typeof obj !== "object") return undefined
  const v = (obj as Record<string, unknown>)[key]
  if (typeof v === "string") return v
  if (typeof v === "number") return String(v)
  return undefined
}

export function readRecordNumber(obj: unknown, key: string): number | undefined {
  if (!obj || typeof obj !== "object") return undefined
  const v = (obj as Record<string, unknown>)[key]
  if (typeof v === "number" && Number.isFinite(v)) return v
  if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Number(v)
  return undefined
}

export function normalizeProjectListPayload(data: unknown): unknown[] {
  if (Array.isArray(data)) return data
  if (data && typeof data === "object") {
    const o = data as Record<string, unknown>
    if (Array.isArray(o.projects)) return o.projects
    if (Array.isArray(o.items)) return o.items
    if (Array.isArray(o.results)) return o.results
  }
  return []
}

export function formatIsoWhenPresent(iso: string | undefined): string {
  if (!iso?.trim()) return "—"
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}
