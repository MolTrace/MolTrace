/**
 * Optional method / model / scoring / threshold fields echoed by analysis APIs.
 * Reads common snake_case and camelCase keys without renaming request paths or wire formats.
 */

import type { EvidenceItem } from "@/src/lib/spectracheck/evidence-types"

export type MethodProvenanceFields = Pick<
  EvidenceItem,
  | "methodId"
  | "methodName"
  | "methodVersion"
  | "modelVersionId"
  | "modelName"
  | "modelVersion"
  | "scoringProfileId"
  | "scoringProfileName"
  | "thresholdProfileId"
  | "thresholdProfileName"
>

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

/** Flatten payload + nested objects that may carry provenance (read-only). */
function flattenRecordSources(...sources: unknown[]): Record<string, unknown>[] {
  const out: Record<string, unknown>[] = []
  for (const s of sources) {
    if (!isRecord(s)) continue
    out.push(s)
    for (const key of ["method_provenance", "methodProvenance", "metadata", "meta", "context"]) {
      const n = s[key]
      if (isRecord(n)) out.push(n)
    }
  }
  return out
}

function firstString(rs: Record<string, unknown>[], keys: string[]): string | undefined {
  for (const r of rs) {
    for (const k of keys) {
      const v = r[k]
      if (typeof v === "string" && v.trim()) return v.trim()
      if (typeof v === "number" && Number.isFinite(v)) return String(v)
    }
  }
  return undefined
}

/**
 * Merge provenance from API payloads (evidence rows, analysis responses, metadata nests).
 */
export function extractMethodProvenanceFromUnknown(...sources: unknown[]): Partial<MethodProvenanceFields> {
  const rs = flattenRecordSources(...sources)
  const out: Partial<MethodProvenanceFields> = {}

  const mid = firstString(rs, ["method_id", "methodId"])
  if (mid) out.methodId = mid
  const mn = firstString(rs, ["method_name", "methodName"])
  if (mn) out.methodName = mn
  const mv = firstString(rs, ["method_version", "methodVersion"])
  if (mv) out.methodVersion = mv

  const mvid = firstString(rs, ["model_version_id", "modelVersionId"])
  if (mvid) out.modelVersionId = mvid
  const mname = firstString(rs, ["model_name", "modelName"])
  if (mname) out.modelName = mname
  const mver = firstString(rs, ["model_version", "modelVersion"])
  if (mver) out.modelVersion = mver

  const spid = firstString(rs, ["scoring_profile_id", "scoringProfileId"])
  if (spid) out.scoringProfileId = spid
  const spn = firstString(rs, ["scoring_profile_name", "scoringProfileName"])
  if (spn) out.scoringProfileName = spn

  const tpid = firstString(rs, ["threshold_profile_id", "thresholdProfileId"])
  if (tpid) out.thresholdProfileId = tpid
  const tpn = firstString(rs, ["threshold_profile_name", "thresholdProfileName"])
  if (tpn) out.thresholdProfileName = tpn

  return out
}

export function hasMethodProvenanceFields(item: EvidenceItem): boolean {
  return Boolean(
    item.methodId ||
      item.methodName ||
      item.methodVersion ||
      item.modelVersionId ||
      item.modelName ||
      item.modelVersion ||
      item.scoringProfileId ||
      item.scoringProfileName ||
      item.thresholdProfileId ||
      item.thresholdProfileName,
  )
}
