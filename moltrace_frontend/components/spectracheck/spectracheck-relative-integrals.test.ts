import { describe, expect, it } from "vitest"
import {
  findRelativeIntegralDisclosure,
  isRelativeIntegralDisclosure,
  relabelRelativeIntegrals,
} from "@/components/spectracheck/spectracheck-relative-integrals"

/**
 * Verbatim copy of ``nmrcheck.integration_scale.RELATIVE_INTEGRAL_DISCLOSURE``.
 * Kept whole rather than trimmed to an anchor so a backend reword shows up here
 * as a failing test rather than as a notice that silently stops rendering.
 */
const DISCLOSURE =
  "These integrals are relative. With no structure to set a proton budget, the " +
  "smallest resolved signal is set to 1 H and every other signal is reported as " +
  "a multiple of it, so the values are ratios between signals rather than proton " +
  "counts. Supply a valid structure to scale them to its proton budget."

describe("isRelativeIntegralDisclosure", () => {
  it("recognises the backend disclosure", () => {
    expect(isRelativeIntegralDisclosure(DISCLOSURE)).toBe(true)
  })

  it("does not fire on the ordinary solvent and impurity warnings", () => {
    const others = [
      "Residual CDCl3 detected at 7.26 ppm.",
      "Observed aromatic integration is 3.2 H against an expected 2 H.",
      "Fewer than 3 paired peaks — linear scaling skipped.",
      "Baseline correction did not converge; integrals may be inflated.",
    ]
    for (const warning of others) {
      expect(isRelativeIntegralDisclosure(warning)).toBe(false)
    }
  })
})

describe("findRelativeIntegralDisclosure", () => {
  it("finds it at the top level", () => {
    expect(findRelativeIntegralDisclosure({ warnings: [DISCLOSURE] })).toBe(DISCLOSURE)
  })

  it("finds it inside a preview or analysis block", () => {
    expect(findRelativeIntegralDisclosure({ preview: { warnings: [DISCLOSURE] } })).toBe(DISCLOSURE)
    expect(findRelativeIntegralDisclosure({ analysis: { warnings: [DISCLOSURE] } })).toBe(DISCLOSURE)
  })

  it("returns null when the integrals were grounded by a structure", () => {
    expect(findRelativeIntegralDisclosure({ warnings: ["Residual CDCl3 at 7.26 ppm."] })).toBeNull()
    expect(findRelativeIntegralDisclosure({ warnings: [] })).toBeNull()
    expect(findRelativeIntegralDisclosure(null)).toBeNull()
    expect(findRelativeIntegralDisclosure({})).toBeNull()
  })
})

describe("relabelRelativeIntegrals", () => {
  it("relabels the integral suffix emitted by _peaks_to_nmr_text", () => {
    const text = "5.23 (d, J = 3.6 Hz, 12.5H), 3.95 (ddd, J = 10.3, 4.6, 2.6 Hz, 9.5H)"
    expect(relabelRelativeIntegrals(text)).toBe(
      "5.23 (d, J = 3.6 Hz, 12.5 rel.), 3.95 (ddd, J = 10.3, 4.6, 2.6 Hz, 9.5 rel.)",
    )
  })

  it("relabels an integer integral and the ungrounded three-digit case", () => {
    expect(relabelRelativeIntegrals("7.26 (s, 123.5H)")).toBe("7.26 (s, 123.5 rel.)")
    expect(relabelRelativeIntegrals("2.10 (s, 3H)")).toBe("2.10 (s, 3 rel.)")
  })

  it("leaves J couplings in Hz alone", () => {
    const text = "5.23 (d, J = 3.6 Hz, 1H)"
    expect(relabelRelativeIntegrals(text)).toBe("5.23 (d, J = 3.6 Hz, 1 rel.)")
    expect(relabelRelativeIntegrals(text)).toContain("3.6 Hz")
  })

  it("leaves a nucleus label alone", () => {
    // "1H NMR (500 MHz, CDCl3)" — the H follows a digit but not a closing
    // parenthesis, which is the whole reason the pattern anchors on ")".
    expect(relabelRelativeIntegrals("1H NMR (500 MHz, CDCl3)")).toBe("1H NMR (500 MHz, CDCl3)")
  })
})
