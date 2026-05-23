export type SpectrumYRange = {
  yMin: number
  yMax: number
}

type SpectrumYRangeOptions = {
  lowerQuantile?: number
  upperQuantile?: number
  paddingRatio?: number
  /**
   * Baseline noise scale (σ) for the trace, typically the median |Δy| between
   * consecutive baseline samples. When supplied, the lower y-axis bound is
   * clamped to at most ``noiseFloorSigmas × noiseFloor`` below zero so that
   * pathological negative dispersion lobes around saturated solvent / aromatic
   * peaks fall *below* the visible frame instead of protruding through the
   * baseline.
   *
   * This mirrors Mestrenova's display convention: the GSD peak picker defaults
   * to ``Peaks Type: Only Positive`` (MNova manual §8.2.2) and the displayed
   * frame floors near the noise envelope so dispersion artefacts never appear
   * as negative peaks under the baseline. Honest baseline noise (a few × σ)
   * stays visible because it sits inside the clamp.
   */
  noiseFloor?: number
  /**
   * Multiplier on ``noiseFloor`` for the clamp. Defaults to 4 — wide enough
   * for honest 3σ-4σ noise tails to remain inside the visible frame while
   * truncating anything deeper as artefact.
   */
  noiseFloorSigmas?: number
}

/**
 * Robust display range for 1D spectra.
 *
 * NMR uploads often contain one enormous solvent/water spike plus a baseline
 * with small negative excursions. Plotting from y=0 clips the bottom of the
 * real trace; plotting to the absolute max compresses the analyte region. This
 * helper keeps the ordinary spectrum visible by using robust lower/upper
 * quantiles and adding headroom on both sides.
 *
 * When a ``noiseFloor`` (baseline σ) is supplied, the lower bound is *also*
 * clamped at ``-noiseFloorSigmas × noiseFloor`` so that large negative
 * dispersion lobes near saturated solvent / aromatic peaks do not push the
 * visible frame down with them — Mestrenova-style "Only Positive" display.
 */
export function robustSpectrumYRange(
  values: ArrayLike<number>,
  options: SpectrumYRangeOptions = {},
): SpectrumYRange {
  const lowerQuantile = options.lowerQuantile ?? 0.01
  const upperQuantile = options.upperQuantile ?? 0.99
  const paddingRatio = options.paddingRatio ?? 0.12
  const noiseFloor = options.noiseFloor
  const noiseFloorSigmas = options.noiseFloorSigmas ?? 4
  const finite: number[] = []

  for (let i = 0; i < values.length; i++) {
    const v = values[i]
    if (Number.isFinite(v)) finite.push(v)
  }

  if (finite.length === 0) {
    return { yMin: -1, yMax: 1 }
  }

  let low: number
  let high: number
  if (finite.length < 100) {
    low = Number.POSITIVE_INFINITY
    high = Number.NEGATIVE_INFINITY
    for (const v of finite) {
      if (v < low) low = v
      if (v > high) high = v
    }
  } else {
    finite.sort((a, b) => a - b)
    const last = finite.length - 1
    const lowIndex = Math.min(last, Math.max(0, Math.floor(last * lowerQuantile)))
    const highIndex = Math.min(last, Math.max(0, Math.ceil(last * upperQuantile)))
    low = finite[lowIndex]
    high = finite[highIndex]
  }

  if (!Number.isFinite(low) || !Number.isFinite(high)) {
    return { yMin: -1, yMax: 1 }
  }
  if (low > high) {
    const tmp = low
    low = high
    high = tmp
  }

  const reference = Math.max(Math.abs(low), Math.abs(high), 1)
  let span = high - low
  if (!Number.isFinite(span) || span <= reference * 1e-9) {
    const center = (low + high) / 2
    const halfSpan = reference * 0.05
    low = center - halfSpan
    high = center + halfSpan
    span = high - low
  }

  const pad = Math.max(span * paddingRatio, reference * 0.01)
  let yMin = low - pad
  const yMax = high + pad

  // Noise-floor clamp. With ``noiseFloor`` supplied we keep yMin *no deeper*
  // than ``-noiseFloorSigmas × noiseFloor`` so a few-σ noise envelope stays
  // visible (honest baseline) while solvent/aromatic dispersion lobes that
  // dip far below get clipped off the bottom of the frame — Mnova convention.
  if (
    typeof noiseFloor === "number" &&
    Number.isFinite(noiseFloor) &&
    noiseFloor > 0
  ) {
    const clampedFloor = -noiseFloorSigmas * noiseFloor
    if (yMin < clampedFloor) {
      yMin = clampedFloor
    }
  }

  if (!Number.isFinite(yMin) || !Number.isFinite(yMax) || yMax <= yMin) {
    return { yMin: -1, yMax: 1 }
  }
  return { yMin, yMax }
}

export function combineSpectrumYRanges(ranges: SpectrumYRange[]): SpectrumYRange {
  if (ranges.length === 0) return { yMin: -1, yMax: 1 }
  let yMin = Number.POSITIVE_INFINITY
  let yMax = Number.NEGATIVE_INFINITY
  for (const range of ranges) {
    if (Number.isFinite(range.yMin) && range.yMin < yMin) yMin = range.yMin
    if (Number.isFinite(range.yMax) && range.yMax > yMax) yMax = range.yMax
  }
  if (!Number.isFinite(yMin) || !Number.isFinite(yMax) || yMax <= yMin) {
    return { yMin: -1, yMax: 1 }
  }
  return { yMin, yMax }
}
