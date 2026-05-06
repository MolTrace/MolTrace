import type { ReactNode } from "react"
import { describe, expect, it } from "vitest"
import { renderHook, act } from "@testing-library/react"
import { SpectraCheckEvidenceProvider, useSpectraCheckEvidence } from "@/src/lib/spectracheck/useSpectraCheckEvidence"

function wrapper({ children }: { children: ReactNode }) {
  return <SpectraCheckEvidenceProvider>{children}</SpectraCheckEvidenceProvider>
}

describe("useSpectraCheckEvidence", () => {
  it("adds, selects, filters, and clears evidence items", () => {
    const { result } = renderHook(
      () => {
        const ev = useSpectraCheckEvidence()
        return ev
      },
      { wrapper },
    )

    let id = ""
    act(() => {
      id = result.current.addEvidenceItem({
        layer: "hrms_exact_mass",
        title: "HRMS match",
        sourceTab: "MS Evidence",
        status: "ready",
        response: { ok: true },
      })
    })

    expect(id.length).toBeGreaterThan(0)
    expect(result.current.evidenceItems).toHaveLength(1)
    expect(result.current.getEvidenceByLayer("hrms_exact_mass")).toHaveLength(1)
    expect(result.current.getSelectedEvidenceItems()).toHaveLength(0)

    act(() => {
      result.current.toggleSelectedForUnified(id)
    })
    expect(result.current.getSelectedEvidenceItems()).toHaveLength(1)

    act(() => {
      result.current.updateEvidenceItem(id, { summary: "updated" })
    })
    expect(result.current.evidenceItems[0]?.summary).toBe("updated")

    act(() => {
      result.current.removeEvidenceItem(id)
    })
    expect(result.current.evidenceItems).toHaveLength(0)

    act(() => {
      result.current.addEvidenceItem({
        layer: "formula_search",
        title: "Formula",
        sourceTab: "MS Evidence",
        status: "ready",
        response: {},
      })
      result.current.clearEvidenceItems()
    })
    expect(result.current.evidenceItems).toHaveLength(0)
  })

  it("selectAllForUnified selects every item", () => {
    const { result } = renderHook(() => useSpectraCheckEvidence(), { wrapper })

    act(() => {
      result.current.addEvidenceItem({
        layer: "hrms_exact_mass",
        title: "A",
        sourceTab: "MS Evidence",
        status: "ready",
        response: {},
      })
      result.current.addEvidenceItem({
        layer: "formula_search",
        title: "B",
        sourceTab: "MS Evidence",
        status: "ready",
        response: {},
      })
    })
    expect(result.current.getSelectedEvidenceItems()).toHaveLength(0)

    act(() => {
      result.current.selectAllForUnified()
    })
    expect(result.current.evidenceItems.every((e) => e.selectedForUnified)).toBe(true)
  })

  it("replaceEvidenceItems replaces the queue", () => {
    const { result } = renderHook(() => useSpectraCheckEvidence(), { wrapper })

    act(() => {
      result.current.addEvidenceItem({
        layer: "hrms_exact_mass",
        title: "A",
        sourceTab: "MS Evidence",
        status: "ready",
        response: {},
      })
    })
    expect(result.current.evidenceItems).toHaveLength(1)

    act(() => {
      result.current.replaceEvidenceItems([])
    })
    expect(result.current.evidenceItems).toHaveLength(0)
  })

  it("stores latest unified confidence result for report handoff", () => {
    const { result } = renderHook(() => useSpectraCheckEvidence(), { wrapper })

    expect(result.current.latestUnifiedConfidenceResult).toBeNull()

    act(() => {
      result.current.setLatestUnifiedConfidenceResult({ confidence_score: 0.9 })
    })
    expect(result.current.latestUnifiedConfidenceResult).toEqual({ confidence_score: 0.9 })

    act(() => {
      result.current.setLatestUnifiedConfidenceResult(null)
    })
    expect(result.current.latestUnifiedConfidenceResult).toBeNull()
  })

  it("stores latest report result for workflow / compose handoff", () => {
    const { result } = renderHook(() => useSpectraCheckEvidence(), { wrapper })

    expect(result.current.latestReportResult).toBeNull()

    act(() => {
      result.current.setLatestReportResult({ json_report: { ok: true }, html_report: "<p>x</p>" })
    })
    expect(result.current.latestReportResult).toEqual({ json_report: { ok: true }, html_report: "<p>x</p>" })

    act(() => {
      result.current.setLatestReportResult(null)
    })
    expect(result.current.latestReportResult).toBeNull()
  })
})
