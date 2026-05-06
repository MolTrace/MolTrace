/**
 * ML model/registry provenance — reads API field names (snake_case) and camelCase mirrors
 * from nested response objects without renaming wire formats.
 */

export type MlModelProvenanceFields = {
  modelArtifactId?: number
  datasetVersionId?: number
  evaluationRunId?: number
  deploymentCandidateId?: number
  modelCardId?: number
  modelName?: string
  modelVersion?: string
  methodId?: string
  approvalStatus?: string
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function flattenMlSources(...sources: unknown[]): Record<string, unknown>[] {
  const out: Record<string, unknown>[] = []
  for (const s of sources) {
    if (!isRecord(s)) continue
    out.push(s)
    for (const key of [
      "ml_provenance",
      "mlProvenance",
      "ml_model_provenance",
      "mlModelProvenance",
      "model_ml_provenance",
      "registry_provenance",
      "metadata_json",
      "metadata",
      "meta",
      "context",
      "method_provenance",
      "methodProvenance",
      "payload",
      "result",
      "answer",
    ]) {
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

function firstPositiveInt(rs: Record<string, unknown>[], keys: string[]): number | undefined {
  for (const r of rs) {
    for (const k of keys) {
      const v = r[k]
      if (typeof v === "number" && Number.isFinite(v) && v >= 1) return Math.floor(v)
      if (typeof v === "string" && v.trim()) {
        const n = Number.parseInt(v, 10)
        if (Number.isFinite(n) && n >= 1) return n
      }
    }
  }
  return undefined
}

/** Merge ML provenance echoes from arbitrary API payloads into a normalized shape. */
export function extractMlModelProvenanceFromUnknown(...sources: unknown[]): Partial<MlModelProvenanceFields> {
  const rs = flattenMlSources(...sources)
  const out: Partial<MlModelProvenanceFields> = {}

  const mid = firstString(rs, ["method_id", "methodId"])
  if (mid) out.methodId = mid

  const mname = firstString(rs, ["model_name", "modelName"])
  if (mname) out.modelName = mname
  const mver = firstString(rs, ["model_version", "modelVersion"])
  if (mver) out.modelVersion = mver

  const maid = firstPositiveInt(rs, ["model_artifact_id", "modelArtifactId"])
  if (maid != null) out.modelArtifactId = maid
  const dvid = firstPositiveInt(rs, ["dataset_version_id", "datasetVersionId"])
  if (dvid != null) out.datasetVersionId = dvid
  const erid = firstPositiveInt(rs, ["evaluation_run_id", "evaluationRunId"])
  if (erid != null) out.evaluationRunId = erid
  const dcid = firstPositiveInt(rs, ["deployment_candidate_id", "deploymentCandidateId"])
  if (dcid != null) out.deploymentCandidateId = dcid
  const mcid = firstPositiveInt(rs, ["model_card_id", "modelCardId"])
  if (mcid != null) out.modelCardId = mcid

  const approv =
    firstString(rs, ["approval_status", "approvalStatus", "model_card_approval_status", "deployment_approval_status"]) ??
    undefined
  if (approv) out.approvalStatus = approv

  return out
}

export function mergeMlModelProvenancePreferItem(
  fromItem: Partial<MlModelProvenanceFields>,
  ...sources: unknown[]
): Partial<MlModelProvenanceFields> {
  const fromNested = extractMlModelProvenanceFromUnknown(...sources)
  return {
    ...fromNested,
    ...Object.fromEntries(
      Object.entries(fromItem).filter(([, v]) => v !== undefined && v !== null && v !== ""),
    ),
  }
}

/** True when any modeled registry/model field beyond generic method-only strings is recorded. */
export function hasRenderableMlRegistryProvenance(f: Partial<MlModelProvenanceFields>): boolean {
  return Boolean(
    f.modelArtifactId != null ||
      f.datasetVersionId != null ||
      f.evaluationRunId != null ||
      f.deploymentCandidateId != null ||
      f.modelCardId != null ||
      (f.modelName?.trim().length ?? 0) > 0 ||
      (f.modelVersion?.trim().length ?? 0) > 0 ||
      (f.methodId?.trim().length ?? 0) > 0 ||
      (f.approvalStatus?.trim().length ?? 0) > 0,
  )
}
