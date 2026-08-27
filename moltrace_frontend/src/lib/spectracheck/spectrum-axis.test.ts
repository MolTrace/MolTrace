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

  /**
   * Peak apexes must fit inside the frame.
   *
   * The upper bound was the 99th percentile of ALL samples. In an NMR spectrum
   * peaks are a tiny minority of samples — the overwhelming majority are
   * baseline — so a 99th percentile lands barely above the noise, and every
   * peak apex above it is drawn flat-topped against the top of the frame. A
   * flat-topped peak is the "blob" a chemist reports.
   *
   * Measured on 3 real Bruker 13C datasets before this changed: the frame top
   * sat at 22.4% / 22.2% / 9.8% of the tallest analyte peak, with 16 / 19 / 18
   * displayed samples outside the frame.
   *
   * The genuine concern the percentile was reaching for — one enormous solvent
   * spike squashing the analyte region into a few pixels — is handled upstream
   * by the dominant-peak mask, which removes that peak's samples BEFORE this
   * function sees them. Clamping again here only clips real analyte peaks.
   */
  function nmrShapedTrace() {
    // 1,000 samples: baseline noise everywhere, sharp peaks on ~1% of points.
    const values: number[] = []
    for (let i = 0; i < 1000; i++) {
      values.push(((i * 37) % 11) / 1000 - 0.005) // deterministic +/-0.005 noise
    }
    for (const [index, amplitude] of [[120, 1.0], [430, 0.62], [700, 0.35]] as const) {
      values[index] = amplitude
      values[index - 1] = amplitude * 0.45
      values[index + 1] = amplitude * 0.45
    }
    return values
  }

  it("keeps every peak apex inside the frame", () => {
    const values = nmrShapedTrace()
    const observedMax = Math.max(...values)
    const range = robustSpectrumYRange(values)
    expect(range.yMax).toBeGreaterThanOrEqual(observedMax)
  })

  it("puts the frame top above the tallest peak, not a fraction of it", () => {
    const values = nmrShapedTrace()
    const tallest = Math.max(...values)
    const range = robustSpectrumYRange(values, { noiseFloor: 0.005 })
    // Previously this ratio measured ~0.1-0.22 on real data: the frame top sat
    // BELOW the tallest peak, so its apex was clipped flat.
    expect(range.yMax / tallest).toBeGreaterThanOrEqual(1)
  })

  it("still clips deep negative excursions off the bottom", () => {
    // The lower bound keeps its quantile + noise-floor clamp: dispersion lobes
    // below the baseline are a different, well-justified case, and this change
    // must not reopen them.
    const values = nmrShapedTrace()
    values[500] = -8
    const range = robustSpectrumYRange(values, { noiseFloor: 0.005 })
    expect(range.yMin).toBeGreaterThan(-1)
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
