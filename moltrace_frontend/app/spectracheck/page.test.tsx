import { render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { SpectraCheckWorkspace } from "@/components/spectracheck/spectracheck-workspace"
import {
  SPECTRACHECK_EVIDENCE_SESSION_KEY,
  invalidateSpectraCheckSessionReadCache,
} from "@/src/lib/spectracheck/spectracheck-evidence-session"

vi.mock("next/navigation", () => ({
  usePathname: () => "/spectracheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))

describe("spectracheck page", () => {
  beforeEach(() => {
    window.localStorage.clear()
    invalidateSpectraCheckSessionReadCache()
  })
  afterEach(() => {
    window.localStorage.clear()
    invalidateSpectraCheckSessionReadCache()
  })

  it("renders analysis button and core input textareas", () => {
    const view = render(<SpectraCheckWorkspace defaultTab="tab-nmr-text" />)

    expect(screen.getByLabelText("Candidate structures")).toBeInTheDocument()
    expect(screen.getByLabelText("1H NMR text")).toBeInTheDocument()
    expect(screen.getByLabelText("13C NMR text")).toBeInTheDocument()

    view.unmount()
    render(<SpectraCheckWorkspace defaultTab="tab-predicted" />)
    expect(
      screen.getByRole("button", { name: /Run 1H \/ 13C evidence match/i }),
    ).toBeInTheDocument()
  })

  it("defaults the candidate structures in Methanol → Ethanol → Propanol order", () => {
    render(<SpectraCheckWorkspace defaultTab="tab-nmr-text" />)
    const textarea = screen.getByLabelText("Candidate structures") as HTMLTextAreaElement
    const value = textarea.value
    const lines = value.split(/\r?\n/).map((l) => l.trim()).filter(Boolean)
    expect(lines).toHaveLength(3)
    expect(lines[0]).toMatch(/^Methanol\s*\|/)
    expect(lines[1]).toMatch(/^Ethanol\s*\|/)
    expect(lines[2]).toMatch(/^Propanol\s*\|/)
  })

  it("always restores the molecular defaults on mount even if a stale candidate list was persisted", () => {
    // Simulate a previous session where the user replaced the candidate list.
    window.localStorage.setItem(
      SPECTRACHECK_EVIDENCE_SESSION_KEY,
      JSON.stringify({
        v: 1,
        sampleId: "SAMPLE-001",
        solventChoice: "CDCl3",
        customSolvent: "",
        candidatesText: "WrongMolecule | XYZ | manual",
        protonText: "",
        carbonText: "",
        evidenceItems: [],
        latestUnifiedConfidenceResult: null,
      }),
    )
    invalidateSpectraCheckSessionReadCache()

    render(<SpectraCheckWorkspace defaultTab="tab-nmr-text" />)
    const textarea = screen.getByLabelText("Candidate structures") as HTMLTextAreaElement
    expect(textarea.value).toContain("Methanol | CO")
    expect(textarea.value).toContain("Ethanol | CCO")
    expect(textarea.value).toContain("Propanol | CCCO")
    expect(textarea.value).not.toContain("WrongMolecule")
  })
})
