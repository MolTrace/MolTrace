import { describe, expect, it } from "vitest"
import { evidenceApiPayload } from "@/src/lib/spectracheck/spectracheck-backend-session"
import type { EvidenceItem } from "@/src/lib/spectracheck/evidence-types"

/**
 * `evidenceApiPayload` feeds POST/PATCH /spectracheck/sessions/{id}/evidence, whose bodies are
 * validated by SpectraCheckEvidenceCreate / SpectraCheckEvidenceUpdate — both `extra="forbid"`.
 * The camelCase EvidenceItem must be mapped to the snake_case contract; any stray key (or a
 * required-field omission) 422s the whole save. These are the invariants that guard against a
 * regression of that recurring bug class.
 */

// Union of fields accepted by SpectraCheckEvidenceCreate / SpectraCheckEvidenceUpdate.
const ALLOWED_KEYS = new Set([
  "layer",
  "title",
  "source_tab",
  "status",
  "score",
  "label",
  "summary",
  "evidence_summary_json",
  "contradictions_json",
  "warnings_json",
  "notes_json",
  "endpoint",
  "request_preview_json",
  "response_json",
  "selected_for_unified",
  "provenance_json",
  "method_id",
  "model_version_id",
  "scoring_profile_id",
  "threshold_profile_id",
  "provenance_metadata_json",
  "provenance_metadata",
])

// camelCase / client-only keys that must never reach the extra="forbid" model.
const FORBIDDEN_KEYS = [
  "id",
  "createdAt",
  "created_at",
  "sampleId",
  "sample_id",
  "sourceTab",
  "selectedForUnified",
  "response",
  "requestPreview",
  "provenance",
  "evidenceSummary",
  "contradictions",
  "warnings",
  "notes",
  "backendEvidenceId",
  "qcStatus",
  "readinessStatus",
  "overrideStatus",
  "overrideReason",
  "qualityAssessmentId",
  "visualReviewed",
  "methodId",
]

function fullItem(overrides: Partial<EvidenceItem> = {}): EvidenceItem {
  return {
    id: "e1",
    layer: "nmr_text_candidates",
    title: "1H candidates",
    sourceTab: "SpectraCheck",
    sampleId: "S1",
    status: "ready",
    score: 0.87,
    label: "top",
    summary: "looks plausible",
    evidenceSummary: ["3 peaks matched"],
    contradictions: [],
    warnings: ["low S/N"],
    notes: ["reviewer note"],
    endpoint: "/nmr/predict",
    requestPreview: { solvent: "CDCl3" },
    response: { candidates: [{ smiles: "CCO" }] },
    createdAt: "2026-01-01T00:00:00Z",
    selectedForUnified: true,
    provenance: { filename: "a.jdx", sha256: "abc", rawDataPreserved: true },
    backendEvidenceId: 42,
    qcStatus: "qc_pass",
    readinessStatus: "ready_for_unified_evidence",
    overrideStatus: "allow_with_warning",
    overrideReason: "manual sign-off",
    qualityAssessmentId: "qa-9",
    methodId: "method-1",
    ...overrides,
  }
}

describe("evidenceApiPayload", () => {
  it("emits only keys the backend contract allows", () => {
    const payload = evidenceApiPayload(fullItem())
    for (const key of Object.keys(payload)) {
      expect(ALLOWED_KEYS.has(key), `unexpected key "${key}"`).toBe(true)
    }
  })

  it("drops every camelCase / client-only key", () => {
    const payload = evidenceApiPayload(fullItem())
    for (const key of FORBIDDEN_KEYS) {
      expect(payload, `forbidden key "${key}" present`).not.toHaveProperty(key)
    }
  })

  it("always sends the four required strings and the snake_case core fields", () => {
    const payload = evidenceApiPayload(fullItem())
    expect(payload.layer).toBe("nmr_text_candidates")
    expect(payload.title).toBe("1H candidates")
    expect(payload.source_tab).toBe("SpectraCheck")
    expect(payload.status).toBe("ready")
    expect(payload.selected_for_unified).toBe(true)
  })

  it("maps camelCase list/object fields to their *_json counterparts", () => {
    const payload = evidenceApiPayload(fullItem())
    expect(payload.evidence_summary_json).toEqual(["3 peaks matched"])
    expect(payload.contradictions_json).toEqual([])
    expect(payload.warnings_json).toEqual(["low S/N"])
    expect(payload.notes_json).toEqual(["reviewer note"])
    expect(payload.request_preview_json).toEqual({ solvent: "CDCl3" })
    expect(payload.provenance_json).toEqual({ filename: "a.jdx", sha256: "abc", rawDataPreserved: true })
    expect(payload.response_json).toEqual({ candidates: [{ smiles: "CCO" }] })
  })

  it("keeps response_json a dict, wrapping a non-object response", () => {
    const payload = evidenceApiPayload(fullItem({ response: "raw text" }))
    expect(payload.response_json).toEqual({ value: "raw text" })
  })

  it("defaults response_json to {} when the response is nullish", () => {
    const payload = evidenceApiPayload(fullItem({ response: null }))
    expect(payload.response_json).toEqual({})
  })

  it("only sends a score inside the backend's [0, 1] range", () => {
    expect(evidenceApiPayload(fullItem({ score: 0.5 })).score).toBe(0.5)
    expect(evidenceApiPayload(fullItem({ score: 1.5 }))).not.toHaveProperty("score")
    expect(evidenceApiPayload(fullItem({ score: Number.NaN }))).not.toHaveProperty("score")
    expect(evidenceApiPayload(fullItem({ score: undefined }))).not.toHaveProperty("score")
  })

  it("omits optional string fields when blank so a PATCH does not clobber them", () => {
    const payload = evidenceApiPayload(fullItem({ label: "  ", summary: undefined, endpoint: "" }))
    expect(payload).not.toHaveProperty("label")
    expect(payload).not.toHaveProperty("summary")
    expect(payload).not.toHaveProperty("endpoint")
  })

  it("produces a contract-valid body from a minimal item", () => {
    const minimal: EvidenceItem = {
      id: "m1",
      layer: "report",
      title: "t",
      sourceTab: "SpectraCheck",
      status: "ready",
      response: {},
      createdAt: "2026-01-01T00:00:00Z",
      selectedForUnified: false,
    }
    const payload = evidenceApiPayload(minimal)
    for (const key of Object.keys(payload)) {
      expect(ALLOWED_KEYS.has(key), `unexpected key "${key}"`).toBe(true)
    }
    expect(payload.source_tab).toBe("SpectraCheck")
    expect(payload.response_json).toEqual({})
    expect(payload.selected_for_unified).toBe(false)
  })
})
