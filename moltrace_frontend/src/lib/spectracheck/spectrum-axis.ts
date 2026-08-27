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
   * This mirrors the industry-standard NMR display convention: the GSD peak
   * picker defaults to ``Peaks Type: Only Positive`` and the displayed frame
   * floors near the noise envelope so dispersion artefacts never appear
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
 * visible frame down with them — the industry-standard "Only Positive" display.
 */
export function robustSpectrumYRange(
  values: ArrayLike<number>,
  options: SpectrumYRangeOptions = {},
): SpectrumYRange {
  const lowerQuantile = options.lowerQuantile ?? 0.01
  /**
   * The upper bound is the observed MAXIMUM, so no peak apex is ever drawn
   * flat-topped against the top of the frame.
   *
   * This was 0.99, and that is a deliberate reversal rather than a typo fix.
   * The reasoning it replaced — anchoring to the absolute max lets one
   * enormous solvent spike squash the analyte region — is real, but a
   * percentile over ALL samples is the wrong instrument for it. In an NMR
   * spectrum peaks are a tiny minority of samples and baseline is the
   * overwhelming majority, so the 99th percentile lands barely above the noise
   * floor and clips genuine analyte peaks, not just the runaway one. Measured
   * on 3 real Bruker 13C datasets, the frame top sat at 22.4% / 22.2% / 9.8%
   * of the tallest analyte peak, with 16 / 19 / 18 samples outside the frame.
   *
   * The runaway-solvent case is handled upstream instead, by the dominant-peak
   * mask in SpectrumViewer: it removes that peak's samples before this function
   * sees them, and it is a visible, user-controlled toggle rather than a silent
   * clamp. Vertical Gain/yZoom then lift small peaks against a fixed axis,
   * which is how NMR software has always let you inspect weak signal — tall
   * peaks run off the top because the USER scaled them there.
   *
   * The lower bound deliberately keeps its quantile and noise-floor clamp:
   * negative dispersion lobes below the baseline are a separate case, and one
   * this change must not reopen.
   */
  const upperQuantile = options.upperQuantile ?? 1
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
  // dip far below get clipped off the bottom of the frame — standard NMR-display convention.
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
