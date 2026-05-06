/**
 * SpectraCheck backend session API — paths and field names must match the backend contract.
 */

import { apiFetch } from "@/lib/api/client"
import type { EvidenceItem, EvidenceItemStatus, EvidenceLayerType } from "@/src/lib/spectracheck/evidence-types"
import { extractMethodProvenanceFromUnknown } from "@/src/lib/spectracheck/evidence-method-provenance"
import { extractMlModelProvenanceFromUnknown } from "@/src/lib/ml/model-provenance-extract"
import { sanitizeEvidenceItemsForStorage, sanitizeForSpectraCheckStorage } from "@/src/lib/spectracheck/spectracheck-evidence-session"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { NMR_SOLVENT_OPTIONS, NMR_SOLVENT_OTHER_VALUE } from "@/src/lib/nmr/solvents"

function pickFirstString(o: Record<string, unknown>, keys: string[]): string | undefined {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "string" && v.trim()) return v
    if (typeof v === "number") return String(v)
  }
  return undefined
}

export type SharedWorkspaceInputs = {
  sampleId: string
  solventChoice: string
  customSolvent: string
  candidatesText: string
  protonText: string
  carbonText: string
}

export function applySharedInputsFromJson(
  json: unknown,
  setters: {
    setSampleId: (v: string) => void
    setSolventChoice: (v: string) => void
    setCustomSolvent: (v: string) => void
    setCandidatesText: (v: string) => void
    setProtonText: (v: string) => void
    setCarbonText: (v: string) => void
  },
): void {
  if (!json || typeof json !== "object") return
  const o = json as Record<string, unknown>
  const sample = pickFirstString(o, ["sample_id", "sampleId"])
  if (sample) setters.setSampleId(sample)
  const cand = pickFirstString(o, ["candidates_text", "candidatesText"])
  if (cand != null) setters.setCandidatesText(cand)
  const p1 = pickFirstString(o, ["observed_proton_text", "proton_text", "protonText"])
  if (p1 != null) setters.setProtonText(p1)
  const c1 = pickFirstString(o, ["observed_carbon13_text", "carbon_text", "carbonText"])
  if (c1 != null) setters.setCarbonText(c1)
  const sc = pickFirstString(o, ["solvent_choice", "solventChoice"])
  const cs = pickFirstString(o, ["custom_solvent", "customSolvent"]) ?? ""
  const solv = pickFirstString(o, ["solvent"])
  const liquid = sc ?? solv
  if (liquid) {
    const opt = NMR_SOLVENT_OPTIONS.find((x) => x.value === liquid || x.label === liquid)
    if (opt) {
      setters.setSolventChoice(opt.value)
      setters.setCustomSolvent("")
    } else {
      setters.setSolventChoice(NMR_SOLVENT_OTHER_VALUE)
      setters.setCustomSolvent(cs || liquid)
    }
  } else if (cs) {
    setters.setSolventChoice(NMR_SOLVENT_OTHER_VALUE)
    setters.setCustomSolvent(cs)
  }
}

export function buildSharedInputsJson(s: SharedWorkspaceInputs): Record<string, unknown> {
  return {
    sample_id: s.sampleId,
    solvent_choice: s.solventChoice,
    custom_solvent: s.customSolvent,
    candidates_text: s.candidatesText,
    observed_proton_text: s.protonText,
    observed_carbon13_text: s.carbonText,
  }
}

export function parseSessionIdFromRecord(session: unknown): string | undefined {
  if (!session || typeof session !== "object") return undefined
  const o = session as Record<string, unknown>
  return pickFirstString(o, ["id", "session_id", "sessionId"])
}

export function parseSharedInputsJson(session: unknown): unknown {
  if (!session || typeof session !== "object") return null
  const o = session as Record<string, unknown>
  const raw = o.shared_inputs_json
  if (raw && typeof raw === "object") return raw
  if (typeof o.shared_inputs_json === "string") {
    try {
      return JSON.parse(o.shared_inputs_json) as unknown
    } catch {
      return null
    }
  }
  return null
}

export function parseProjectSampleIds(session: unknown): { projectId?: string; sampleId?: string } {
  if (!session || typeof session !== "object") return {}
  const o = session as Record<string, unknown>
  const pid = readRecordNumber(o, "project_id") ?? readRecordNumber(o, "projectId")
  const sid = readRecordString(o, "sample_id") ?? readRecordString(o, "sampleId")
  return {
    projectId: pid != null ? String(pid) : undefined,
    sampleId: sid,
  }
}

const LAYERS: EvidenceLayerType[] = [
  "nmr_text_candidates",
  "processed_1h",
  "processed_13c",
  "raw_fid_1h",
  "raw_fid_13c",
  "dept_apt",
  "nmr_2d",
  "predicted_nmr",
  "spectral_similarity",
  "hrms_exact_mass",
  "formula_search",
  "adduct_isotope",
  "msms_annotation",
  "fragmentation_tree",
  "lcms_import",
  "lcms_feature_detection",
  "lcms_feature_grouping",
  "lcms_feature_family_consensus",
  "lcms_dereplication",
  "lcms_confidence_bridge",
  "unified_confidence",
  "report",
]

function asLayer(v: unknown): EvidenceLayerType {
  if (typeof v === "string" && (LAYERS as readonly string[]).includes(v)) return v as EvidenceLayerType
  return "nmr_text_candidates"
}

function asStatus(v: unknown): EvidenceItemStatus {
  if (v === "ready" || v === "warning" || v === "error" || v === "pending_review") return v
  return "ready"
}

/** Normalize GET /evidence payload to a list of row objects. */
export function normalizeEvidenceResponse(data: unknown): unknown[] {
  if (Array.isArray(data)) return data
  if (data && typeof data === "object") {
    const o = data as Record<string, unknown>
    if (Array.isArray(o.evidence)) return o.evidence
    if (Array.isArray(o.items)) return o.items
    if (Array.isArray(o.records)) return o.records
  }
  return []
}

/**
 * Map one API evidence row to EvidenceItem. Expects optional evidence_id for PATCH.
 */
export function mapApiEvidenceRowToItem(row: unknown, fallbackIndex: number): EvidenceItem | null {
  if (!row || typeof row !== "object") return null
  const o = row as Record<string, unknown>
  const nested = o.item && typeof o.item === "object" ? (o.item as Record<string, unknown>) : o
  const backendEvidenceId =
    readRecordNumber(o, "evidence_id") ?? readRecordNumber(nested, "evidence_id") ?? readRecordNumber(o, "id")
  const id =
    readRecordString(nested, "id") ??
    readRecordString(o, "client_id") ??
    (backendEvidenceId != null ? `bev-${backendEvidenceId}` : `row-${fallbackIndex}`)
  const title = readRecordString(nested, "title") ?? readRecordString(o, "title") ?? "Evidence"
  const layer = asLayer(nested.layer ?? o.layer)
  const sourceTab = readRecordString(nested, "sourceTab") ?? readRecordString(nested, "source_tab") ?? "SpectraCheck"
  const createdAt =
    readRecordString(nested, "createdAt") ?? readRecordString(nested, "created_at") ?? new Date().toISOString()
  const response = nested.response ?? o.response ?? {}
  const item: EvidenceItem = {
    id,
    layer,
    title,
    sourceTab,
    status: asStatus(nested.status ?? o.status),
    response: sanitizeForSpectraCheckStorage(response) as unknown,
    createdAt,
    selectedForUnified: nested.selectedForUnified === true || nested.selected_for_unified === true || o.selected_for_unified === true,
    sampleId: readRecordString(nested, "sampleId") ?? readRecordString(nested, "sample_id"),
    score: readRecordNumber(nested, "score"),
    label: readRecordString(nested, "label"),
    summary: readRecordString(nested, "summary"),
    endpoint: readRecordString(nested, "endpoint"),
    requestPreview:
      nested.requestPreview !== undefined
        ? sanitizeForSpectraCheckStorage(nested.requestPreview)
        : nested.request_preview !== undefined
          ? sanitizeForSpectraCheckStorage(nested.request_preview)
          : undefined,
    provenance:
      nested.provenance && typeof nested.provenance === "object"
        ? (sanitizeForSpectraCheckStorage(nested.provenance) as EvidenceItem["provenance"])
        : undefined,
  }
  if (backendEvidenceId != null) item.backendEvidenceId = backendEvidenceId
  Object.assign(
    item,
    extractMethodProvenanceFromUnknown(nested, o, item.response, nested.response ?? o.response),
    extractMlModelProvenanceFromUnknown(nested, o, item.response, nested.response ?? o.response),
  )
  return item
}

export function mapEvidencePayloadToItems(data: unknown): EvidenceItem[] {
  const rows = normalizeEvidenceResponse(data)
  const out: EvidenceItem[] = []
  rows.forEach((row, i) => {
    const it = mapApiEvidenceRowToItem(row, i)
    if (it) out.push(it)
  })
  return out
}

export function parseUnifiedEvidenceResponse(data: unknown): unknown | null {
  if (data == null) return null
  if (typeof data === "object" && data !== null) {
    const o = data as Record<string, unknown>
    if ("unified_evidence" in o) return sanitizeForSpectraCheckStorage(o.unified_evidence)
    if ("result" in o) return sanitizeForSpectraCheckStorage(o.result)
    if ("payload" in o) return sanitizeForSpectraCheckStorage(o.payload)
  }
  return sanitizeForSpectraCheckStorage(data)
}

export async function fetchSpectraCheckSessionBundle(sessionId: string) {
  const sid = encodeURIComponent(sessionId)
  const [session, evidence, unifiedEvidence, review] = await Promise.all([
    apiFetch<unknown>(`/spectracheck/sessions/${sid}`, { method: "GET" }),
    apiFetch<unknown>(`/spectracheck/sessions/${sid}/evidence`, { method: "GET" }),
    apiFetch<unknown>(`/spectracheck/sessions/${sid}/unified-evidence`, { method: "GET" }),
    apiFetch<unknown>(`/spectracheck/sessions/${sid}/review`, { method: "GET" }),
  ])
  return { session, evidence, unifiedEvidence, review }
}

export async function fetchSpectraCheckSessionsList() {
  return apiFetch<unknown>("/spectracheck/sessions", { method: "GET" })
}

export async function fetchSessionReportsList(sessionId: string) {
  const sid = encodeURIComponent(sessionId)
  return apiFetch<unknown>(`/spectracheck/sessions/${sid}/reports`, { method: "GET" })
}

export async function postSpectraCheckSession(body: unknown) {
  return apiFetch<unknown>("/spectracheck/sessions", { method: "POST", body })
}

export async function patchSpectraCheckSession(sessionId: string, body: unknown) {
  const sid = encodeURIComponent(sessionId)
  return apiFetch<unknown>(`/spectracheck/sessions/${sid}`, { method: "PATCH", body })
}

export function evidenceApiPayload(item: EvidenceItem): Record<string, unknown> {
  const clone: EvidenceItem = { ...item }
  delete clone.backendEvidenceId
  const sanitized = sanitizeEvidenceItemsForStorage([clone])[0] as Record<string, unknown>
  delete sanitized.backendEvidenceId
  return sanitized
}

export async function postSessionEvidence(sessionId: string, item: EvidenceItem) {
  const sid = encodeURIComponent(sessionId)
  return apiFetch<unknown>(`/spectracheck/sessions/${sid}/evidence`, {
    method: "POST",
    body: evidenceApiPayload(item),
  })
}

export async function patchSessionEvidence(sessionId: string, item: EvidenceItem) {
  const sid = encodeURIComponent(sessionId)
  const eid = item.backendEvidenceId
  if (eid == null) throw new Error("Missing backend evidence id for PATCH")
  return apiFetch<unknown>(`/spectracheck/sessions/${sid}/evidence/${encodeURIComponent(String(eid))}`, {
    method: "PATCH",
    body: evidenceApiPayload(item),
  })
}

export async function postUnifiedEvidence(sessionId: string, payload: unknown) {
  const sid = encodeURIComponent(sessionId)
  const body = payload == null ? {} : sanitizeForSpectraCheckStorage(payload)
  return apiFetch<unknown>(`/spectracheck/sessions/${sid}/unified-evidence`, {
    method: "POST",
    body: body ?? {},
  })
}

export async function fetchSessionReview(sessionId: string) {
  const sid = encodeURIComponent(sessionId)
  return apiFetch<unknown>(`/spectracheck/sessions/${sid}/review`, { method: "GET" })
}

export async function fetchSessionAudit(sessionId: string) {
  const sid = encodeURIComponent(sessionId)
  return apiFetch<unknown>(`/spectracheck/sessions/${sid}/audit`, { method: "GET" })
}

export async function postSessionReview(sessionId: string, review: unknown) {
  const sid = encodeURIComponent(sessionId)
  const body = review == null ? {} : sanitizeForSpectraCheckStorage(review)
  return apiFetch<unknown>(`/spectracheck/sessions/${sid}/review`, {
    method: "POST",
    body: body ?? {},
  })
}

export async function fetchSpectraCheckSessionWorkflowRuns(sessionId: string) {
  const sid = encodeURIComponent(sessionId)
  return apiFetch<unknown>(`/spectracheck/sessions/${sid}/workflow-runs`, { method: "GET" })
}
