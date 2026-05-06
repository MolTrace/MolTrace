/**
 * Browser-only persistence for SpectraCheck session fields (localStorage).
 * Does not send data externally. Do not store secrets or raw uploads here.
 */

import type { EvidenceItem } from "@/src/lib/spectracheck/evidence-types"

export const SPECTRACHECK_EVIDENCE_SESSION_KEY = "moltrace:spectracheck:evidence-session"

export type SpectraCheckEvidenceSessionV1 = {
  v: 1
  sampleId: string
  solventChoice: string
  customSolvent: string
  candidatesText: string
  protonText: string
  carbonText: string
  evidenceItems: EvidenceItem[]
  latestUnifiedConfidenceResult: unknown | null
  /** Workflow / compose report handoff for the Report tab (optional for older saved sessions). */
  latestReportResult?: unknown | null
}

let sessionReadCache: SpectraCheckEvidenceSessionV1 | null | undefined

export function invalidateSpectraCheckSessionReadCache(): void {
  sessionReadCache = undefined
}

/** Single read per page load for hydration (provider + workspace share the same snapshot). */
export function consumeSpectraCheckSessionHydration(): SpectraCheckEvidenceSessionV1 | null {
  if (sessionReadCache !== undefined) return sessionReadCache
  sessionReadCache = typeof window !== "undefined" ? loadSpectraCheckEvidenceSession() : null
  return sessionReadCache
}

function jsonReplacer(_key: string, value: unknown): unknown {
  if (value instanceof File || value instanceof Blob) return undefined
  if (typeof FileList !== "undefined" && value instanceof FileList) return undefined
  if (value instanceof ArrayBuffer) return undefined
  if (ArrayBuffer.isView(value)) return undefined
  return value
}

/** Remove binary / file-like payloads; keep JSON-serializable metadata and API summaries. */
export function sanitizeForSpectraCheckStorage(value: unknown): unknown {
  try {
    const s = JSON.stringify(value, jsonReplacer)
    if (s === undefined) return null
    return JSON.parse(s) as unknown
  } catch {
    return null
  }
}

export function sanitizeEvidenceItemsForStorage(items: EvidenceItem[]): EvidenceItem[] {
  return items.map((item) => ({
    ...item,
    response: sanitizeForSpectraCheckStorage(item.response) as unknown,
    requestPreview:
      item.requestPreview !== undefined ? sanitizeForSpectraCheckStorage(item.requestPreview) : undefined,
  })) as EvidenceItem[]
}

function isSessionV1(raw: unknown): raw is SpectraCheckEvidenceSessionV1 {
  if (!raw || typeof raw !== "object") return false
  const o = raw as Record<string, unknown>
  return o.v === 1 && typeof o.sampleId === "string" && Array.isArray(o.evidenceItems)
}

export function loadSpectraCheckEvidenceSession(): SpectraCheckEvidenceSessionV1 | null {
  if (typeof window === "undefined") return null
  try {
    const raw = window.localStorage.getItem(SPECTRACHECK_EVIDENCE_SESSION_KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (!isSessionV1(parsed)) return null
    return {
      ...parsed,
      evidenceItems: sanitizeEvidenceItemsForStorage(parsed.evidenceItems),
      latestUnifiedConfidenceResult:
        parsed.latestUnifiedConfidenceResult != null
          ? sanitizeForSpectraCheckStorage(parsed.latestUnifiedConfidenceResult)
          : null,
    }
  } catch {
    return null
  }
}

export function saveSpectraCheckEvidenceSession(session: SpectraCheckEvidenceSessionV1): void {
  if (typeof window === "undefined") return
  try {
    const payload: SpectraCheckEvidenceSessionV1 = {
      ...session,
      evidenceItems: sanitizeEvidenceItemsForStorage(session.evidenceItems),
      latestUnifiedConfidenceResult:
        session.latestUnifiedConfidenceResult != null
          ? sanitizeForSpectraCheckStorage(session.latestUnifiedConfidenceResult)
          : null,
      latestReportResult:
        session.latestReportResult != null
          ? sanitizeForSpectraCheckStorage(session.latestReportResult)
          : null,
    }
    window.localStorage.setItem(SPECTRACHECK_EVIDENCE_SESSION_KEY, JSON.stringify(payload))
    invalidateSpectraCheckSessionReadCache()
  } catch {
    // Quota or privacy mode — ignore silently
  }
}

export function clearSpectraCheckEvidenceSession(): void {
  if (typeof window === "undefined") return
  try {
    window.localStorage.removeItem(SPECTRACHECK_EVIDENCE_SESSION_KEY)
  } catch {
    // ignore
  }
  invalidateSpectraCheckSessionReadCache()
}
