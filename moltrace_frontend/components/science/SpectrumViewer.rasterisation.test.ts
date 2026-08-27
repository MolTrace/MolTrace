import { describe, expect, it } from "vitest"
import {
  sampleSpectrumTraceForPlot,
  spectrumPointBudgetForWidth,
} from "@/components/science/SpectrumViewer"

/**
 * Rasterisation density — the "blob" invariant.
 *
 * Measured on the shipped raw-FID configuration before this suite existed: the
 * backend sends ~9,173 display points, the call site asked for a 12,000-point
 * budget, so `sampleSpectrumTraceForPlot` took its early return and handed
 * Plotly all 9,171 vertices for a ~900 px chart — 10.19 vertices per pixel
 * column, each column spanning its full local peak-to-peak. Ten overlapping
 * diagonal strokes inside one column rasterise as a soft filled band, which is
 * simultaneously the "blob" over a peak and the fuzzy baseline between peaks.
 *
 * Professional NMR software draws ONE vertical min-to-max segment per pixel
 * column. So the invariant is about DENSITY, not point count: however many
 * points arrive, what Plotly receives must be bounded by the number of pixel
 * columns available to draw them in — and a stretch of pure baseline must
 * collapse toward a single vertex per column rather than an envelope pair.
 *
 * Raising the budget is what broke this, so these tests deliberately assert an
 * upper bound on vertices. The peak-survival test is the counterweight: it
 * fails if a future change fixes density by decimating real signal away.
 */

const PLOT_WIDTH_PX = 900

/** A 1H-like spectrum: flat noisy baseline, one tall solvent line, one doublet. */
function syntheticSpectrum(length: number) {
  const x: number[] = new Array(length)
  const y: number[] = new Array(length)
  const sfoMhz = 400
  const lines: Array<{ ppm: number; amp: number }> = [
    { ppm: 2.05, amp: 50 }, // residual solvent
    { ppm: 7.26 - 3.5 / sfoMhz, amp: 1 }, // doublet, J = 7 Hz
    { ppm: 7.26 + 3.5 / sfoMhz, amp: 1 },
  ]
  const halfWidthPpm = 0.4 / sfoMhz // 0.8 Hz FWHM
  // Deterministic pseudo-noise: a test that changes verdict between runs is
  // worse than no test.
  let seed = 12345
  const noise = () => {
    seed = (seed * 1103515245 + 12345) % 2147483648
    return (seed / 2147483648 - 0.5) * 0.02
  }
  for (let i = 0; i < length; i++) {
    const ppm = 12 - (i / (length - 1)) * 12
    x[i] = ppm
    let v = noise()
    for (const line of lines) {
      const d = ppm - line.ppm
      v += (line.amp * halfWidthPpm * halfWidthPpm) / (d * d + halfWidthPpm * halfWidthPpm)
    }
    y[i] = v
  }
  return { x, y }
}

/* The SHIPPED budget for a plot this wide — no overrides, exactly what the
   raw-FID and processed surfaces now pass. Asserting against the real
   derivation is the point: the sampler was never wrong, the budget handed to
   it was. */
const budgetForWidth = (widthPx: number) => spectrumPointBudgetForWidth(widthPx)

describe("spectrum rasterisation density", () => {
  it("bounds rendered vertices by pixel columns, not by source length", () => {
    const { x, y } = syntheticSpectrum(9173)
    const out = sampleSpectrumTraceForPlot(x, y, {
      maxPoints: budgetForWidth(PLOT_WIDTH_PX),
      xRange: null,
      maskRange: null,
    })

    const verticesPerColumn = out.x.length / PLOT_WIDTH_PX
    // One min/max pair per column is the target; 3.5 leaves headroom for the
    // LTTB slot without allowing the ~10/column band that produced the blob.
    expect(verticesPerColumn).toBeLessThanOrEqual(3.5)
    // And it must genuinely have resampled rather than passed the source through.
    expect(out.x.length).toBeLessThan(9173)
  })

  it("collapses a pure-baseline window toward one vertex per column", () => {
    const { x, y } = syntheticSpectrum(9173)
    const out = sampleSpectrumTraceForPlot(x, y, {
      maxPoints: budgetForWidth(PLOT_WIDTH_PX),
      xRange: null,
      maskRange: null,
    })

    // 9.5-11.5 ppm carries no line in the synthetic spectrum: pure baseline.
    const inWindow = out.x.filter((ppm) => ppm >= 9.5 && ppm <= 11.5).length
    const columnsInWindow = ((11.5 - 9.5) / 12) * PLOT_WIDTH_PX
    // A flat bucket emits ONE representative point, so a baseline stretch must
    // not be drawn as a min/max envelope band.
    expect(inWindow / columnsInWindow).toBeLessThanOrEqual(1.5)
  })

  it("still resolves both lines of a J = 7 Hz doublet at full view", () => {
    const { x, y } = syntheticSpectrum(9173)
    const out = sampleSpectrumTraceForPlot(x, y, {
      maxPoints: budgetForWidth(PLOT_WIDTH_PX),
      xRange: null,
      maskRange: null,
    })

    // Count local maxima inside the doublet window that clear the noise floor.
    const idx: number[] = []
    for (let i = 1; i < out.x.length - 1; i++) {
      const ppm = out.x[i]
      if (ppm < 7.2 || ppm > 7.32) continue
      if (out.y[i] > out.y[i - 1] && out.y[i] >= out.y[i + 1] && out.y[i] > 0.2) idx.push(i)
    }
    expect(idx.length).toBeGreaterThanOrEqual(2)
  })
})
