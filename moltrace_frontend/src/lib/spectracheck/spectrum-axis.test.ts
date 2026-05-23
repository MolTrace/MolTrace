import { describe, expect, it } from "vitest"

import { combineSpectrumYRanges, robustSpectrumYRange } from "./spectrum-axis"

describe("robustSpectrumYRange", () => {
  it("returns a padded range around the lower/upper percentiles", () => {
    // Plain baseline → percentile-based range with padding on both sides.
    // The noise-floor clamp is dormant when no ``noiseFloor`` is supplied.
    const range = robustSpectrumYRange([0, 0.1, -0.05, 0.2, 0.1, 0.0, -0.1, 0.15, 0.05, 0])
    expect(range.yMin).toBeLessThan(-0.1)
    expect(range.yMax).toBeGreaterThan(0.2)
  })

  it("clamps the lower bound near -4σ when a noise floor is supplied", () => {
    // Spectrum with a single huge negative dispersion lobe at index 0,
    // mimicking the residual solvent / aromatic ringing the user wants
    // hidden below the frame. Without ``noiseFloor`` the lower bound is
    // dragged down to that lobe. With ``noiseFloor = 0.05`` the floor
    // clamps to -4σ = -0.2, well above the -10 artefact.
    const values = [
      -10, 0.02, -0.03, 0.01, 0.04, -0.02, 0.03, -0.01, 0.02, 0.0,
      0.01, -0.02, 0.03, 0.0, 0.02, -0.03, 0.04, 0.01, -0.01, 0.05,
      0.01, -0.01, 0.02, 0.03, -0.02, 0.0, 0.01, -0.03, 0.04, 0.02,
      0.0, 0.02, -0.02, 0.01, -0.01, 0.03, 0.0, 0.04, 0.01, 0.02,
      -0.01, 0.0, 0.03, -0.02, 0.01, 0.02, -0.03, 0.04, 0.0, 0.01,
      -0.02, 0.02, 0.01, 0.0, -0.01, 0.03, 0.02, -0.02, 0.01, 0.04,
      0.0, -0.01, 0.02, 0.01, 0.0, 0.03, -0.02, 0.02, 0.01, -0.01,
      0.04, 0.0, -0.02, 0.01, 0.03, 0.02, -0.01, 0.0, 0.02, -0.03,
      0.01, 0.04, 0.0, 0.02, -0.01, 0.03, 0.0, 0.01, -0.02, 0.02,
      0.04, 0.01, 0.0, -0.01, 0.02, 0.03, 0.0, -0.02, 0.01, 0.04,
    ]
    const without = robustSpectrumYRange(values)
    const clamped = robustSpectrumYRange(values, { noiseFloor: 0.05 })
    expect(without.yMin).toBeLessThan(-1) // dragged down by the artefact
    expect(clamped.yMin).toBeGreaterThanOrEqual(-0.21) // -4 × 0.05 = -0.2
    expect(clamped.yMin).toBeLessThan(0) // honest baseline noise still visible
  })

  it("respects a custom noiseFloorSigmas multiplier", () => {
    // Several deep negative artefacts ensure the percentile-based lower
    // bound is well below the clamp at either sigma setting, so the
    // clamp's multiplier directly drives the resulting yMin.
    const baseline = Array.from({ length: 200 }, (_, i) => Math.sin(i) * 0.05)
    for (let i = 0; i < 8; i++) {
      baseline[i] = -20 // deeper than any sigmas × σ clamp considered here
    }
    const at4 = robustSpectrumYRange(baseline, { noiseFloor: 0.05 })
    const at6 = robustSpectrumYRange(baseline, { noiseFloor: 0.05, noiseFloorSigmas: 6 })
    // Both clamps actively engage; -6σ sits deeper than -4σ.
    expect(at4.yMin).toBeCloseTo(-0.2, 6)
    expect(at6.yMin).toBeCloseTo(-0.3, 6)
    expect(at6.yMin).toBeLessThan(at4.yMin)
  })

  it("ignores a non-positive or non-finite noiseFloor", () => {
    const values = [-3, 0.01, -0.02, 0.02, 0.0, 0.01]
    const baseline = robustSpectrumYRange(values)
    const zero = robustSpectrumYRange(values, { noiseFloor: 0 })
    const negative = robustSpectrumYRange(values, { noiseFloor: -0.5 })
    const nan = robustSpectrumYRange(values, { noiseFloor: Number.NaN })
    expect(zero.yMin).toBe(baseline.yMin)
    expect(negative.yMin).toBe(baseline.yMin)
    expect(nan.yMin).toBe(baseline.yMin)
  })
})

describe("combineSpectrumYRanges", () => {
  it("returns the widest of the supplied ranges", () => {
    const combined = combineSpectrumYRanges([
      { yMin: -0.5, yMax: 1.0 },
      { yMin: -0.2, yMax: 2.0 },
    ])
    expect(combined.yMin).toBe(-0.5)
    expect(combined.yMax).toBe(2.0)
  })
})
