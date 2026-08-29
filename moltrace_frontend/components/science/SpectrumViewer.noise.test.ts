import { describe, expect, it } from "vitest"
import { estimateBaselineNoiseSigma } from "@/components/science/SpectrumViewer"

/**
 * The estimator's contract is in its own name: return the sigma of an
 * equivalent Gaussian noise process. For iid N(0, sigma^2) the difference of
 * adjacent samples has sd sigma*sqrt(2), so recovering sigma from a median
 * absolute successive difference needs 1.4826/sqrt(2) ~ 1.0483 — not
 * 1.4826/2 = 0.7413, which returns sigma/sqrt(2) and reads ~29% low.
 */
function gaussianNoise(n: number, sigma: number): number[] {
  // Deterministic Box-Muller; a test that changes verdict between runs is worse
  // than no test.
  let seed = 20260829
  const next = () => {
    seed = (seed * 1103515245 + 12345) % 2147483648
    return seed / 2147483648
  }
  const out: number[] = []
  while (out.length < n) {
    const u = Math.max(next(), 1e-12)
    const v = next()
    out.push(Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v) * sigma)
  }
  return out
}

describe("estimateBaselineNoiseSigma", () => {
  it("recovers sigma from a plain noise series", () => {
    const sigma = estimateBaselineNoiseSigma(gaussianNoise(200_000, 1))
    expect(sigma).toBeGreaterThan(0.95)
    expect(sigma).toBeLessThan(1.05)
  })

  it("scales linearly with the noise it is given", () => {
    const one = estimateBaselineNoiseSigma(gaussianNoise(100_000, 1))
    const ten = estimateBaselineNoiseSigma(gaussianNoise(100_000, 10))
    expect(ten / one).toBeGreaterThan(9.5)
    expect(ten / one).toBeLessThan(10.5)
  })

  it("returns 0 rather than a guess when there is nothing to measure", () => {
    expect(estimateBaselineNoiseSigma([])).toBe(0)
    expect(estimateBaselineNoiseSigma([1, 2])).toBe(0)
    expect(estimateBaselineNoiseSigma([5, 5, 5, 5, 5])).toBe(0)
  })
})
