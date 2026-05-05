import { describe, expect, it, beforeEach } from "vitest"
import {
  SPECTRACHECK_EVIDENCE_SESSION_KEY,
  clearSpectraCheckEvidenceSession,
  invalidateSpectraCheckSessionReadCache,
  loadSpectraCheckEvidenceSession,
  sanitizeForSpectraCheckStorage,
  saveSpectraCheckEvidenceSession,
} from "@/src/lib/spectracheck/spectracheck-evidence-session"
import type { EvidenceItem } from "@/src/lib/spectracheck/evidence-types"

describe("spectracheck-evidence-session", () => {
  beforeEach(() => {
    localStorage.clear()
    invalidateSpectraCheckSessionReadCache()
  })

  it("drops File and Blob from nested payloads", () => {
    const file = new File(["x"], "t.txt", { type: "text/plain" })
    const out = sanitizeForSpectraCheckStorage({
      a: 1,
      f: file,
      nested: { b: new Blob(["y"]) },
    }) as Record<string, unknown>
    expect(out.a).toBe(1)
    expect(out.f).toBeUndefined()
    expect(out.nested).toEqual({})
  })

  it("round-trips v1 session via localStorage", () => {
    const item: EvidenceItem = {
      id: "e1",
      layer: "hrms_exact_mass",
      title: "HRMS",
      sourceTab: "MS Evidence",
      status: "ready",
      response: { ok: true, mz: 123.45 },
      createdAt: "2026-01-01T00:00:00.000Z",
      selectedForUnified: true,
    }
    saveSpectraCheckEvidenceSession({
      v: 1,
      sampleId: "S-1",
      solventChoice: "CDCl3",
      customSolvent: "",
      candidatesText: "A | B | C",
      protonText: "1H …",
      carbonText: "13C …",
      evidenceItems: [item],
      latestUnifiedConfidenceResult: { confidence_score: 0.5 },
    })
    expect(localStorage.getItem(SPECTRACHECK_EVIDENCE_SESSION_KEY)).toBeTruthy()
    const loaded = loadSpectraCheckEvidenceSession()
    expect(loaded?.sampleId).toBe("S-1")
    expect(loaded?.evidenceItems).toHaveLength(1)
    expect(loaded?.evidenceItems[0]?.title).toBe("HRMS")
    expect(loaded?.latestUnifiedConfidenceResult).toEqual({ confidence_score: 0.5 })
  })

  it("clearSpectraCheckEvidenceSession removes the key", () => {
    localStorage.setItem(SPECTRACHECK_EVIDENCE_SESSION_KEY, "{}")
    clearSpectraCheckEvidenceSession()
    expect(localStorage.getItem(SPECTRACHECK_EVIDENCE_SESSION_KEY)).toBeNull()
  })
})
