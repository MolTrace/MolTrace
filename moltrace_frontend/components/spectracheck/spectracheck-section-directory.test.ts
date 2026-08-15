import { describe, expect, it } from "vitest"
import {
  SPECTRACHECK_NAV,
  SPECTRACHECK_SECTIONS,
  isSpectraCheckSection,
} from "@/components/spectracheck/spectracheck-section-directory"

describe("the SpectraCheck section directory", () => {
  it("flattens every nav section exactly once", () => {
    const fromNav = SPECTRACHECK_NAV.flatMap((group) => group.sections.map((s) => s.value))
    expect(SPECTRACHECK_SECTIONS.map((s) => s.value)).toEqual(fromNav)
    expect(new Set(fromNav).size).toBe(fromNav.length)
  })

  it("validates ?section= values against the sections that actually exist", () => {
    // These specific values are the deep-link contract: links carrying them are saved outside
    // the app, so renaming one is a breaking change. The test makes a rename fail loudly.
    expect(isSpectraCheckSection("tab-session")).toBe(true)
    expect(isSpectraCheckSection("tab-overview")).toBe(true)
    expect(isSpectraCheckSection("tab-dev-json")).toBe(true)
    expect(isSpectraCheckSection("not-a-section")).toBe(false)
    expect(isSpectraCheckSection(null)).toBe(false)
    expect(isSpectraCheckSection(undefined)).toBe(false)
  })

  it("keeps every stage label non-empty so the palette rows always name their stage", () => {
    for (const section of SPECTRACHECK_SECTIONS) {
      expect(section.label.trim().length).toBeGreaterThan(0)
      expect(section.stage.trim().length).toBeGreaterThan(0)
    }
  })
})
