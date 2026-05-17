export type SpectrumYRange = {
  yMin: number
  yMax: number
}

type SpectrumYRangeOptions = {
  lowerQuantile?: number
  upperQuantile?: number
  paddingRatio?: number
}

/**
 * Robust display range for 1D spectra.
 *
 * NMR uploads often contain one enormous solvent/water spike plus a baseline
 * with small negative excursions. Plotting from y=0 clips the bottom of the
 * real trace; plotting to the absolute max compresses the analyte region. This
 * helper keeps the ordinary spectrum visible by using robust lower/upper
 * quantiles and adding headroom on both sides.
 */
export function robustSpectrumYRange(
  values: ArrayLike<number>,
  options: SpectrumYRangeOptions = {},
): SpectrumYRange {
  const lowerQuantile = options.lowerQuantile ?? 0.01
  const upperQuantile = options.upperQuantile ?? 0.99
  const paddingRatio = options.paddingRatio ?? 0.12
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
  const yMin = low - pad
  const yMax = high + pad

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
