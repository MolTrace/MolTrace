"use client"

import dynamic from "next/dynamic"
import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from "react"

// Dynamic, client-side-only Plotly import. The dynamic boundary keeps the
// SSR shell light and ensures react-plotly.js never sees ``window`` at
// build time. ``memo`` wraps it so a parent re-render that doesn't change
// any prop reference is a no-op — this is the React-side half of keeping
// the chart non-shaky during sibling state churn.
const Plot = memo(
  dynamic(() => import("react-plotly.js"), { ssr: false }) as React.ComponentType<
    Record<string, unknown>
  >,
) as React.ComponentType<Record<string, unknown>>
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import { cn } from "@/lib/utils"
import {
  PEAK_CATEGORY_DEFAULT_COLOR,
  humanizePeakCategory,
  plotColorForCategory,
} from "@/src/lib/spectracheck/peak-category-style"
import {
  combineSpectrumYRanges,
  robustSpectrumYRange,
} from "@/src/lib/spectracheck/spectrum-axis"
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Droplets,
  Expand,
  Eye,
  EyeOff,
  Hand,
  Layers,
  Maximize2,
  Minimize2,
  Minus,
  Plus,
  RotateCcw,
  ZoomIn,
  ZoomOut,
} from "lucide-react"

/** Peak annotations from backend (no frontend picking).
 *
 * ``category`` is the enriched peak category from
 * ``peak_categorization.PEAK_CATEGORIES`` (aromatic_alkene, aliphatic,
 * labile_OH_NH_SH, …). Optional — when supplied, peaks are color-coded on the
 * chart by category so reviewers can see aromatic / aliphatic / labile groups
 * at a glance. See ``peak-category-style.ts`` for the palette.
 */
export type SpectrumPeakAnnotation = {
  ppm: number
  intensity?: number
  label?: string
  category?: string
}

export type SpectrumOverlays = {
  predicted?: {
    x: number[]
    y: number[]
    label?: string
  }
}

export type SpectrumViewerProps = {
  x: number[]
  y: number[]
  peaks?: SpectrumPeakAnnotation[]
  overlays?: SpectrumOverlays
  /** Reserved for titles / accessibility when wiring experiment context */
  nucleus?: "1H" | "13C"
  xLabel?: string
  yLabel?: string
  reversedXAxis?: boolean
  renderMode?: "svg" | "webgl"
  /**
   * Display-only raw FID cleanup for aromatic windows. It smooths the
   * baseline/base samples around 6.45-8.65 ppm (1H) and 105-165 ppm (13C)
   * while preserving detected peak apices, so the raw archive remains
   * immutable and processed spectra are not touched.
   */
  rawFidAromaticBaseSmoothing?: boolean
  /**
   * Optional observed-trace sampling budget. Processed spectra use the compact
   * defaults; raw FID can opt into a denser Plotly trace so fine multiplet
   * structure is visible without zooming.
   */
  maxObservedPoints?: number
  observedPointsPerPixel?: number
  /** Initial visibility for peak category markers and their legend. */
  defaultShowPeaks?: boolean
  /** Initial visibility for vertical peak guides and ppm labels (industry-standard NMR display). */
  defaultShowPeakGuides?: boolean
  className?: string
}

const DISPLAY_Y_CAP = 1e120
const MIN_VIEWPORT_TRACE_POINTS = 1_000
const MAX_VIEWPORT_TRACE_POINTS = 3_000
const VIEWPORT_POINTS_PER_PIXEL = 2
const MAX_OVERLAY_TRACE_POINTS = 1_800
const AROMATIC_BASE_WINDOWS = [
  { min: 6.45, max: 8.65 },
  { min: 105, max: 165 },
] as const
const AROMATIC_BASE_PEAK_NOISE_MULTIPLIER = 3.5
const AROMATIC_BASE_LOCAL_PEAK_NOISE_MULTIPLIER = 1.6
const AROMATIC_BASE_FLOOR_NOISE_MULTIPLIER = 0.55

/**
 * Plotly plot-area inset, in pixels. Shared by the layout (so Plotly draws the
 * traces inside this box) AND by the custom hover readout (so cursor-x maps to
 * exactly the ppm Plotly rendered). Keeping a single source of truth is what
 * makes the hover crosshair land on the spectrum line rather than near it.
 */
const PLOT_MARGIN = { l: 52, r: 16, t: 8, b: 44 } as const
const CONTEXT_MENU_PADDING = 8
const CONTEXT_MENU_ESTIMATED_WIDTH = 240
const CONTEXT_MENU_ESTIMATED_HEIGHT = 520

type PlotlyAxisLike = {
  _offset?: number
  _length?: number
  p2l?: (px: number) => unknown
  p2c?: (px: number) => unknown
}

type PlotlyGraphDivLike = {
  _fullLayout?: {
    xaxis?: PlotlyAxisLike
    yaxis?: PlotlyAxisLike
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), Math.max(min, max))
}

function spectrumContextMenuMaxHeight(): number | undefined {
  if (typeof window === "undefined") return undefined
  const viewport = window.visualViewport
  const height = viewport?.height ?? window.innerHeight
  return Math.max(160, Math.floor(height - CONTEXT_MENU_PADDING * 2))
}

function clampSpectrumContextMenuPosition(
  x: number,
  y: number,
  width = CONTEXT_MENU_ESTIMATED_WIDTH,
  height = CONTEXT_MENU_ESTIMATED_HEIGHT,
): { x: number; y: number } {
  if (typeof window === "undefined") return { x, y }
  const viewport = window.visualViewport
  const left = viewport?.offsetLeft ?? 0
  const top = viewport?.offsetTop ?? 0
  const viewportWidth = viewport?.width ?? window.innerWidth
  const viewportHeight = viewport?.height ?? window.innerHeight
  const availableWidth = Math.max(1, viewportWidth - CONTEXT_MENU_PADDING * 2)
  const availableHeight = Math.max(1, viewportHeight - CONTEXT_MENU_PADDING * 2)
  const clampedWidth = Math.min(width, availableWidth)
  const clampedHeight = Math.min(height, availableHeight)
  return {
    x: clamp(
      x,
      left + CONTEXT_MENU_PADDING,
      left + viewportWidth - CONTEXT_MENU_PADDING - clampedWidth,
    ),
    y: clamp(
      y,
      top + CONTEXT_MENU_PADDING,
      top + viewportHeight - CONTEXT_MENU_PADDING - clampedHeight,
    ),
  }
}

type PlotPointerShift = {
  crosshairLeft: number
  ppm: number
}

function axisPixelBounds(
  axis: PlotlyAxisLike | null | undefined,
  fallbackStart: number,
  fallbackEnd: number,
): [number, number] {
  const offset = axis?._offset
  const length = axis?._length
  if (
    typeof offset === "number" &&
    typeof length === "number" &&
    Number.isFinite(offset) &&
    Number.isFinite(length) &&
    length > 1
  ) {
    return [offset, offset + length]
  }
  return [fallbackStart, fallbackEnd]
}

function ppmFromPlotlyAxis(axis: PlotlyAxisLike | null | undefined, pxWithinAxis: number): number | null {
  const convert = axis?.p2l ?? axis?.p2c
  if (typeof convert !== "function") return null
  const ppm = Number(convert.call(axis, pxWithinAxis))
  return Number.isFinite(ppm) ? ppm : null
}

export function chemicalShiftFromPlotPointer({
  pointerX,
  paneWidth,
  effectiveXMin,
  effectiveXMax,
  reversedXAxis,
  margin = PLOT_MARGIN,
  plotlyXAxis,
}: {
  pointerX: number
  paneWidth: number
  effectiveXMin: number
  effectiveXMax: number
  reversedXAxis: boolean
  margin?: typeof PLOT_MARGIN
  plotlyXAxis?: PlotlyAxisLike | null
}): PlotPointerShift | null {
  const [plotLeft, plotRight] = axisPixelBounds(plotlyXAxis, margin.l, paneWidth - margin.r)
  const plotWidth = plotRight - plotLeft
  const span = effectiveXMax - effectiveXMin
  if (
    plotWidth <= 1 ||
    !Number.isFinite(pointerX) ||
    !Number.isFinite(paneWidth) ||
    !Number.isFinite(effectiveXMin) ||
    !Number.isFinite(effectiveXMax) ||
    !Number.isFinite(span) ||
    span === 0
  ) {
    return null
  }
  const crosshairLeft = Math.min(Math.max(pointerX, plotLeft), plotRight)
  const frac = (crosshairLeft - plotLeft) / plotWidth
  const plotlyPpm = ppmFromPlotlyAxis(plotlyXAxis, crosshairLeft - plotLeft)
  return {
    crosshairLeft,
    ppm: plotlyPpm ?? (reversedXAxis ? effectiveXMax - frac * span : effectiveXMin + frac * span),
  }
}

/** Exponential mapping: slider 0..1 → multiplier 1..50000. */
function gainMultiplier(gainSlider01: number): number {
  return Math.exp(gainSlider01 * Math.log(50001))
}

/**
 * Scale source y-array by combined gain × yZoom for display.
 * Both controls multiply the peak heights — this is what users see grow
 * vertically when they drag the slider or click "Taller peaks".
 */
function scaleDisplayYValue(v: number, total: number): number {
  if (Number.isNaN(v)) return Number.NaN
  const raw = v * total
  if (!Number.isFinite(raw)) return 0
  return Math.min(Math.sign(raw) * Math.min(Math.abs(raw), DISPLAY_Y_CAP), DISPLAY_Y_CAP)
}

function medianSorted(values: number[]): number {
  if (values.length === 0) return 0
  const mid = Math.floor(values.length / 2)
  return values.length % 2 === 0 ? (values[mid - 1] + values[mid]) / 2 : values[mid]
}

function robustMedian(values: number[]): number {
  if (values.length === 0) return 0
  const sorted = values.slice().sort((a, b) => a - b)
  return medianSorted(sorted)
}

function robustNoiseFromResiduals(values: number[], center: number): number {
  if (values.length < 3) return 0
  const residuals = values.map((v) => Math.abs(v - center)).sort((a, b) => a - b)
  const madNoise = medianSorted(residuals) * 1.4826

  const deltas: number[] = []
  let previous: number | null = null
  for (const value of values) {
    if (previous != null) deltas.push(Math.abs(value - previous))
    previous = value
  }
  deltas.sort((a, b) => a - b)
  const deltaNoise = deltas.length > 0 ? medianSorted(deltas) * 0.7413 : 0
  return Math.max(madNoise, deltaNoise, 1e-12)
}

/**
 * Whole-spectrum baseline noise σ estimator, robust to peaks and dispersion
 * artefacts. The median |Δy| between consecutive finite samples is dominated
 * by baseline noise — peaks are a sparse minority — so it tracks the noise
 * floor reliably across NMR uploads of any size or dynamic range.
 *
 * Scaled by 1/Φ⁻¹(3/4) ≈ 0.7413 so the returned value is the σ of an
 * equivalent Gaussian noise process, matching the industry-standard
 * noise-factor peak threshold convention used by NMR-processing software.
 */
function estimateBaselineNoiseSigma(values: ArrayLike<number>): number {
  if (values.length < 4) return 0
  const deltas: number[] = []
  let previous: number | null = null
  for (let i = 0; i < values.length; i++) {
    const value = values[i]
    if (!Number.isFinite(value)) {
      previous = null
      continue
    }
    if (previous != null) deltas.push(Math.abs(value - previous))
    previous = value
  }
  if (deltas.length === 0) return 0
  deltas.sort((a, b) => a - b)
  const sigma = medianSorted(deltas) * 0.7413
  return Number.isFinite(sigma) && sigma > 0 ? sigma : 0
}

/**
 * Local display cleanup for raw FID aromatic regions (industry-standard NMR display).
 *
 * Constraints:
 * - only acts inside aromatic windows (1H: 6.45-8.65 ppm; 13C: 105-165 ppm);
 * - preserves peak apices and local maxima above the measured noise floor;
 * - smooths only baseline/base samples using neighbouring non-peak points;
 * - lifts base-only negative excursions to the local noise floor.
 *
 * This is deliberately display-only. It never mutates uploaded FID data,
 * picked peaks, processed spectra, or non-aromatic ppm regions.
 */
export function smoothRawFidAromaticBaseForDisplay(x: number[], y: number[]): number[] {
  const n = Math.min(x.length, y.length)
  if (n < 16) return y

  let out: number[] | null = null

  for (const window of AROMATIC_BASE_WINDOWS) {
    const source = out ?? y
    const regionIndices: number[] = []
    const regionValues: number[] = []
    for (let i = 0; i < n; i++) {
      const ppm = x[i]
      const value = source[i]
      if (!Number.isFinite(ppm) || !Number.isFinite(value)) continue
      if (ppm < window.min || ppm > window.max) continue
      regionIndices.push(i)
      regionValues.push(value)
    }
    if (regionIndices.length < 12) continue

    const baseline = robustMedian(regionValues)
    const noise = robustNoiseFromResiduals(regionValues, baseline)
    if (!Number.isFinite(noise) || noise <= 0) continue

    const strongPeakCutoff = baseline + AROMATIC_BASE_PEAK_NOISE_MULTIPLIER * noise
    const localPeakCutoff = baseline + AROMATIC_BASE_LOCAL_PEAK_NOISE_MULTIPLIER * noise
    const floor = baseline - AROMATIC_BASE_FLOOR_NOISE_MULTIPLIER * noise
    const target: number[] = out ?? y.slice()
    out = target

    const isProtectedPeak = (index: number): boolean => {
      const value = source[index]
      if (!Number.isFinite(value)) return false
      if (value >= strongPeakCutoff) return true
      if (value < localPeakCutoff) return false

      let left = value
      for (let i = index - 1; i >= 0; i--) {
        if (x[i] < window.min || x[i] > window.max) break
        if (Number.isFinite(source[i])) {
          left = source[i]
          break
        }
      }
      let right = value
      for (let i = index + 1; i < n; i++) {
        if (x[i] < window.min || x[i] > window.max) break
        if (Number.isFinite(source[i])) {
          right = source[i]
          break
        }
      }
      return value >= left && value >= right
    }

    const protectedPeaks = new Set<number>()
    for (const index of regionIndices) {
      if (isProtectedPeak(index)) protectedPeaks.add(index)
    }

    for (let pos = 0; pos < regionIndices.length; pos++) {
      const index = regionIndices[pos]
      const value = source[index]
      if (!Number.isFinite(value) || protectedPeaks.has(index)) continue

      let weighted = 0
      let weightSum = 0
      for (let offset = -3; offset <= 3; offset++) {
        const neighbourPos = pos + offset
        if (neighbourPos < 0 || neighbourPos >= regionIndices.length) continue
        const neighbourIndex = regionIndices[neighbourPos]
        if (protectedPeaks.has(neighbourIndex)) continue
        const neighbour = source[neighbourIndex]
        if (!Number.isFinite(neighbour)) continue
        if (neighbour > strongPeakCutoff) continue
        const weight = 4 - Math.abs(offset)
        weighted += neighbour * weight
        weightSum += weight
      }
      if (weightSum === 0) continue

      const localBase = weighted / weightSum
      const blended = value * 0.35 + localBase * 0.65
      target[index] = Math.max(blended, floor)
    }
  }

  return out ?? y
}

/**
 * Detect the contiguous y-axis spike around the absolute-maximum sample and
 * return the indices [start, end] of the spike, or null if no spike dominates.
 *
 * "Spike" = a contiguous run of samples whose |y| stays above
 * ``MASK_SPIKE_FLOOR_MULTIPLIER × P95(|y|)``. A spike is only considered
 * dominant if its peak is at least
 * ``MASK_DOMINANCE_RATIO × P95(|y|)`` — otherwise the spectrum doesn't
 * have a runaway solvent peak and there's nothing to mask.
 *
 * The width is also capped at ``MASK_MAX_WIDTH_FRACTION`` of the full x
 * range so a peak that genuinely is broad (e.g. polymer averaging) isn't
 * over-masked.
 */
const MASK_DOMINANCE_RATIO = 30
const MASK_SPIKE_FLOOR_MULTIPLIER = 3
const MASK_MAX_WIDTH_FRACTION = 0.08

function detectDominantPeakRange(
  x: ArrayLike<number>,
  y: ArrayLike<number>,
): { startIndex: number; endIndex: number; centerPpm: number } | null {
  const n = x.length
  if (n !== y.length || n < 50) return null

  // Collect finite |y| values once for both percentile + max.
  const abs = new Float64Array(n)
  let valid = 0
  let maxAbs = 0
  let maxIdx = 0
  for (let i = 0; i < n; i++) {
    const v = y[i]
    if (!Number.isFinite(v)) continue
    const a = v < 0 ? -v : v
    abs[valid++] = a
    if (a > maxAbs) {
      maxAbs = a
      maxIdx = i
    }
  }
  if (valid === 0 || maxAbs === 0) return null

  // P95 of |y| for dominance ratio.
  const sorted = Array.from(abs.subarray(0, valid))
  sorted.sort((a, b) => a - b)
  const p95 = sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))]
  if (p95 <= 0) return null
  if (maxAbs < MASK_DOMINANCE_RATIO * p95) {
    // No single peak dominates — leave the spectrum alone.
    return null
  }

  // Walk outward from maxIdx until |y| drops below the spike floor.
  const floor = MASK_SPIKE_FLOOR_MULTIPLIER * p95
  let start = maxIdx
  while (start > 0) {
    const v = y[start - 1]
    if (!Number.isFinite(v)) break
    if (Math.abs(v) < floor) break
    start--
  }
  let end = maxIdx
  while (end < n - 1) {
    const v = y[end + 1]
    if (!Number.isFinite(v)) break
    if (Math.abs(v) < floor) break
    end++
  }

  // Cap the masked width so we never blank out more than a small fraction
  // of the visible spectrum.
  const xMinFinite = (x[0] as number) ?? 0
  const xMaxFinite = (x[n - 1] as number) ?? xMinFinite + 1
  const fullSpan = Math.abs(xMaxFinite - xMinFinite) || 1
  const maxSpan = fullSpan * MASK_MAX_WIDTH_FRACTION
  while (Math.abs((x[end] as number) - (x[start] as number)) > maxSpan && end > start + 2) {
    // Shrink whichever side is farther from the maximum.
    const distLow = Math.abs((x[maxIdx] as number) - (x[start] as number))
    const distHigh = Math.abs((x[end] as number) - (x[maxIdx] as number))
    if (distLow > distHigh) start++
    else end--
  }

  return {
    startIndex: start,
    endIndex: end,
    centerPpm: x[maxIdx] as number,
  }
}

function nearestYAtPpm(x: number[], yDisplay: number[], ppm: number): number {
  if (x.length === 0) return 0
  let best = 0
  let bestD = Infinity
  for (let i = 0; i < x.length; i++) {
    const d = Math.abs(x[i] - ppm)
    if (d < bestD) {
      bestD = d
      best = yDisplay[i] ?? 0
    }
  }
  return best
}

export function nearestSourcePointAtPpm(
  x: number[],
  yDisplay: number[],
  ppm: number,
  maskRange?: { startIndex: number; endIndex: number } | null,
): { index: number; ppm: number; intensity: number } | null {
  const n = Math.min(x.length, yDisplay.length)
  if (n === 0 || !Number.isFinite(ppm)) return null

  let ascending = true
  let descending = true
  let allFinite = true
  for (let i = 1; i < n; i++) {
    const previous = x[i - 1]
    const current = x[i]
    if (!Number.isFinite(previous) || !Number.isFinite(current)) {
      allFinite = false
      break
    }
    if (current < previous) ascending = false
    if (current > previous) descending = false
  }

  let bestIndex = -1
  if (allFinite && (ascending || descending)) {
    const target = ascending ? ppm : -ppm
    let low = 0
    let high = n
    while (low < high) {
      const mid = Math.floor((low + high) / 2)
      const value = ascending ? x[mid] : -x[mid]
      if (value < target) low = mid + 1
      else high = mid
    }
    const candidates = [low - 1, low]
    let bestDistance = Infinity
    for (const index of candidates) {
      if (index < 0 || index >= n) continue
      const distance = Math.abs(x[index] - ppm)
      if (distance < bestDistance) {
        bestDistance = distance
        bestIndex = index
      }
    }
  } else {
    let bestDistance = Infinity
    for (let i = 0; i < n; i++) {
      const xv = x[i]
      if (!Number.isFinite(xv)) continue
      const distance = Math.abs(xv - ppm)
      if (distance < bestDistance) {
        bestDistance = distance
        bestIndex = i
      }
    }
  }

  if (bestIndex < 0) return null
  const intensity =
    isMaskedIndex(bestIndex, maskRange) || !Number.isFinite(yDisplay[bestIndex])
      ? Number.NaN
      : yDisplay[bestIndex]
  return { index: bestIndex, ppm: x[bestIndex], intensity }
}

export type SampledSpectrumTrace = {
  x: number[]
  y: number[]
  sampled: boolean
  method: "none" | "viewport_min_max_lttb"
  sourceLength: number
  visibleLength: number
  meanBinSize: number | null
}

/** Cursor readout shown by the custom (Plotly-free) hover overlay. */
type HoverReadout = {
  /** Crosshair x, in pixels from the chart pane's left edge. */
  crosshairLeft: number
  /** Plot-area top/bottom in pixels — the crosshair spans this. */
  plotTop: number
  plotBottom: number
  /** Pane width, used to flip the readout chip away from the edge. */
  paneWidth: number
  /** Chemical shift (ppm) at the cursor according to the rendered x-axis. */
  ppm: number
  /** Source intensity at the nearest source sample (NaN when masked). */
  intensity: number
}

type SampleSpectrumTraceOptions = {
  maxPoints: number
  xRange?: readonly [number, number] | null
  maskRange?: { startIndex: number; endIndex: number } | null
}

function isMaskedIndex(index: number, maskRange: { startIndex: number; endIndex: number } | null | undefined) {
  return Boolean(maskRange && index >= maskRange.startIndex && index <= maskRange.endIndex)
}

function finiteUnmaskedY(y: number[], index: number, maskRange: { startIndex: number; endIndex: number } | null | undefined) {
  if (isMaskedIndex(index, maskRange)) return null
  const value = y[index]
  return Number.isFinite(value) ? value : null
}

function averageBucketPoint(
  x: number[],
  y: number[],
  visibleIndices: number[],
  start: number,
  end: number,
  maskRange: { startIndex: number; endIndex: number } | null | undefined,
): { x: number; y: number } {
  let sx = 0
  let sy = 0
  let count = 0
  for (let i = start; i < end; i++) {
    const index = visibleIndices[i]
    const yv = finiteUnmaskedY(y, index, maskRange)
    const xv = x[index]
    if (yv == null || !Number.isFinite(xv)) continue
    sx += xv
    sy += yv
    count++
  }
  if (count === 0) {
    const fallbackIndex = visibleIndices[Math.max(0, Math.min(visibleIndices.length - 1, start))] ?? 0
    return { x: x[fallbackIndex] ?? 0, y: finiteUnmaskedY(y, fallbackIndex, maskRange) ?? 0 }
  }
  return { x: sx / count, y: sy / count }
}

/**
 * Plotly-resampler-style min/max envelope for browser rendering.
 *
 * NMR spectra often have very narrow spikes. Plain stride sampling can skip
 * those peaks entirely, so each bucket contributes both its local min and
 * max in source order. That keeps peak shape visible while capping the trace
 * size Plotly receives.
 */
export function sampleSpectrumTraceForPlot(
  x: number[],
  y: number[],
  { maxPoints, xRange, maskRange }: SampleSpectrumTraceOptions,
): SampledSpectrumTrace {
  const sourceLength = Math.min(x.length, y.length)
  if (sourceLength === 0) {
    return {
      x: [],
      y: [],
      sampled: false,
      method: "none",
      sourceLength,
      visibleLength: 0,
      meanBinSize: null,
    }
  }

  const hasRange = xRange != null
  const hasMask = maskRange != null
  const clampedMaxPoints = Math.max(4, maxPoints)
  if (!hasRange && !hasMask && sourceLength <= clampedMaxPoints) {
    return { x, y, sampled: false, method: "none", sourceLength, visibleLength: sourceLength, meanBinSize: null }
  }

  const low = hasRange ? Math.min(xRange[0], xRange[1]) : Number.NEGATIVE_INFINITY
  const high = hasRange ? Math.max(xRange[0], xRange[1]) : Number.POSITIVE_INFINITY
  const visibleIndices: number[] = []
  for (let i = 0; i < sourceLength; i++) {
    const xv = x[i]
    if (!Number.isFinite(xv)) continue
    if (xv < low || xv > high) continue
    visibleIndices.push(i)
  }

  const visibleLength = visibleIndices.length
  if (visibleLength === 0) {
    return {
      x: [],
      y: [],
      sampled: false,
      method: "none",
      sourceLength,
      visibleLength: 0,
      meanBinSize: null,
    }
  }

  if (visibleLength <= clampedMaxPoints) {
    const sx: number[] = []
    const sy: number[] = []
    for (const index of visibleIndices) {
      sx.push(x[index])
      sy.push(isMaskedIndex(index, maskRange) ? Number.NaN : y[index])
    }
    return {
      x: sx,
      y: sy,
      sampled: false,
      method: "none",
      sourceLength,
      visibleLength,
      meanBinSize: null,
    }
  }

  const sx: number[] = []
  const sy: number[] = []
  let lastAdded = -1

  const addPoint = (index: number) => {
    if (index < 0 || index === lastAdded) return
    sx.push(x[index])
    sy.push(isMaskedIndex(index, maskRange) ? Number.NaN : y[index])
    lastAdded = index
  }

  addPoint(visibleIndices[0])
  // Robust noise scale for the visible window: the median |Δy| between
  // consecutive finite samples. Baseline noise dominates this median (peaks
  // are a small minority of points), so it tracks the noise floor. Buckets
  // whose dynamic range stays within a few × this scale are flat baseline —
  // they are emitted as a single representative point instead of a min/max
  // pair, so the baseline renders as a calm line and peaks resolve smoothly
  // onto it rather than rising out of a zig-zag envelope band.
  let noiseScale = 0
  {
    const deltas: number[] = []
    let previous: number | null = null
    for (let i = 0; i < visibleLength; i++) {
      const value = y[visibleIndices[i]]
      if (!Number.isFinite(value)) {
        previous = null
        continue
      }
      if (previous != null) deltas.push(Math.abs(value - previous))
      previous = value
    }
    if (deltas.length > 0) {
      deltas.sort((a, b) => a - b)
      noiseScale = deltas[Math.floor(deltas.length / 2)]
    }
  }
  const flatBucketSpread = noiseScale * 6
  let anchorIndex = visibleIndices.find((index) => finiteUnmaskedY(y, index, maskRange) != null) ?? visibleIndices[0]
  const pointSlotsPerBucket = hasMask ? 4 : 3
  const bucketCount = Math.max(1, Math.floor((clampedMaxPoints - 2) / pointSlotsPerBucket))
  const meanBinSize = visibleLength / bucketCount
  for (let bucket = 0; bucket < bucketCount; bucket++) {
    const start = Math.floor((bucket * visibleLength) / bucketCount)
    const end = Math.min(
      visibleLength,
      Math.max(start + 1, Math.floor(((bucket + 1) * visibleLength) / bucketCount)),
    )
    const nextStart = Math.min(visibleLength - 1, end)
    const nextEnd = Math.min(
      visibleLength,
      Math.max(nextStart + 1, Math.floor(((bucket + 2) * visibleLength) / bucketCount)),
    )
    const nextAvg = averageBucketPoint(x, y, visibleIndices, nextStart, nextEnd, maskRange)
    const ax = x[anchorIndex] ?? 0
    const ay = finiteUnmaskedY(y, anchorIndex, maskRange) ?? 0
    let minIndex = -1
    let maxIndex = -1
    let lttbIndex = -1
    let maskIndex = -1
    let minY = Number.POSITIVE_INFINITY
    let maxY = Number.NEGATIVE_INFINITY
    let maxArea = Number.NEGATIVE_INFINITY

    for (let j = start; j < end; j++) {
      const index = visibleIndices[j]
      if (isMaskedIndex(index, maskRange)) {
        if (maskIndex === -1) maskIndex = index
        continue
      }
      const yv = y[index]
      const xv = x[index]
      if (!Number.isFinite(yv) || !Number.isFinite(xv)) continue
      if (yv < minY) {
        minY = yv
        minIndex = index
      }
      if (yv > maxY) {
        maxY = yv
        maxIndex = index
      }
      const area = Math.abs((ax - nextAvg.x) * (yv - ay) - (ax - xv) * (nextAvg.y - ay))
      if (area > maxArea) {
        maxArea = area
        lttbIndex = index
      }
    }

    // Flat baseline bucket → one representative point (the LTTB pick already
    // favours the most informative sample). Bucket with real dynamic range →
    // keep the full min/max[/mask] envelope so narrow peaks always survive.
    const bucketIsFlat =
      maskIndex === -1 &&
      minIndex >= 0 &&
      maxIndex >= 0 &&
      Number.isFinite(minY) &&
      Number.isFinite(maxY) &&
      maxY - minY <= flatBucketSpread
    const bucketIndices = bucketIsFlat
      ? [lttbIndex >= 0 ? lttbIndex : maxIndex]
      : Array.from(new Set([minIndex, maxIndex, lttbIndex, maskIndex]))
          .filter((index) => index >= 0)
          .sort((a, b) => a - b)
    for (const index of bucketIndices) addPoint(index)
    for (let i = bucketIndices.length - 1; i >= 0; i--) {
      const index = bucketIndices[i]
      if (finiteUnmaskedY(y, index, maskRange) != null) {
        anchorIndex = index
        break
      }
    }
  }
  addPoint(visibleIndices[visibleLength - 1])

  return {
    x: sx,
    y: sy,
    sampled: true,
    method: "viewport_min_max_lttb",
    sourceLength,
    visibleLength,
    meanBinSize,
  }
}

function formatSampleBinSize(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`
  if (value >= 10) return String(Math.round(value))
  return value.toFixed(1)
}

function traceNameWithResampling(label: string, sample: SampledSpectrumTrace): string {
  if (!sample.sampled || sample.meanBinSize == null) return label
  return `${label} [R] ~${formatSampleBinSize(sample.meanBinSize)} samples`
}

function SpectrumViewerImpl({
  x,
  y,
  peaks = [],
  overlays,
  nucleus,
  xLabel = "ppm",
  yLabel = "Intensity",
  reversedXAxis = true,
  renderMode = "svg",
  rawFidAromaticBaseSmoothing = false,
  maxObservedPoints = MAX_VIEWPORT_TRACE_POINTS,
  observedPointsPerPixel = VIEWPORT_POINTS_PER_PIXEL,
  defaultShowPeaks = false,
  defaultShowPeakGuides = false,
  className,
}: SpectrumViewerProps) {
  // Default gain01 = 0 → multiplier 1×, so the entire spectrum fits within the
  // chart's baseline y-axis on initial render and after a Full-spectrum reset.
  const [gain01, setGain01] = useState(0)
  const [showPeaks, setShowPeaks] = useState(defaultShowPeaks)
  const [showPeakGuides, setShowPeakGuides] = useState(defaultShowPeakGuides)
  const [showPredicted, setShowPredicted] = useState(true)
  const [contextMenuPosition, setContextMenuPosition] = useState<{ x: number; y: number } | null>(null)
  const contextMenuOpen = contextMenuPosition !== null
  // Mask the dominant solvent / water peak (e.g. HDO at ~4.79 in D2O) so
  // the rest of the spectrum is visible. Auto-enabled — uses the runtime
  // detector below to decide whether a mask is actually needed.
  const [maskDominantPeak, setMaskDominantPeak] = useState(true)
  // Compact mode (default) keeps the chart at ~360 px so the rest of Step 3
  // (KPI tiles, picked peaks, evidence panels) remains on screen. The user
  // can expand it via the toolbar when they need more vertical room for
  // manipulation.
  const [expanded, setExpanded] = useState(false)
  // yZoom is a discrete-step companion to gain01. Both multiply sampled y values so peaks visibly grow.
  const [yZoom, setYZoom] = useState(1)
  const [moveMode, setMoveMode] = useState(false)
  // Custom hover readout (chemical shift + intensity at the cursor). Kept as
  // its own state so a hover update re-renders ONLY the lightweight overlay
  // below — never Plotly's data/layout — which is what keeps the chart stable.
  const [hoverReadout, setHoverReadout] = useState<HoverReadout | null>(null)
  const chartPaneRef = useRef<HTMLDivElement | null>(null)
  const contextMenuRef = useRef<HTMLDivElement | null>(null)
  const [plotPixelWidth, setPlotPixelWidth] = useState(1_200)
  const displaySourceY = useMemo(
    () => (rawFidAromaticBaseSmoothing ? smoothRawFidAromaticBaseForDisplay(x, y) : y),
    [rawFidAromaticBaseSmoothing, x, y],
  )
  // Detect the runaway peak ONCE on the raw input (gain-independent). The
  // detector returns null when no peak is more than MASK_DOMINANCE_RATIO×P95.
  const dominantPeakRange = useMemo(
    () => detectDominantPeakRange(x, displaySourceY),
    [x, displaySourceY],
  )

  // Tie the resampling target to the actual rendered viewport, not the raw
  // spectrum length. This is the React/Plotly equivalent of plotly-resampler's
  // callback budget: a 600 px chart gets ~1200 points, a wide chart tops out
  // at 3000. Resize updates are coarse-grained so scrolling sibling panels
  // cannot thrash Plotly with tiny width oscillations.
  useEffect(() => {
    const el = chartPaneRef.current
    if (!el || typeof ResizeObserver === "undefined") return
    let raf = 0
    const commitWidth = (width: number) => {
      const rounded = Math.max(320, Math.round(width))
      setPlotPixelWidth((current) => (Math.abs(current - rounded) >= 48 ? rounded : current))
    }
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width
      if (!Number.isFinite(width)) return
      window.cancelAnimationFrame(raf)
      raf = window.requestAnimationFrame(() => commitWidth(width))
    })
    observer.observe(el)
    commitWidth(el.getBoundingClientRect().width)
    return () => {
      window.cancelAnimationFrame(raf)
      observer.disconnect()
    }
  }, [])

  /**
   * The y-axis range is anchored to the BASELINE (un-scaled) source data. When
   * gain or yZoom go up, plotted y values increase but the range stays fixed,
   * so peaks visibly grow taller instead of Plotly rescaling the labels.
   *
   * The lower bound is as important as the upper bound: raw/processed spectra
   * routinely have small negative baseline excursions. A [0, yMax] axis chops
   * the base of those peaks, which makes the preview look truncated rather
   * than like a real spectrum.
   */
  const { xMin, xMax, yMin, yMax } = useMemo(() => {
    // Single-pass iterative scan. Replaces Math.min/max(...spread) — the spread
    // operator hits the JS argument-count limit on long arrays (~50k+ items)
    // and throws RangeError, freezing the spectrum render entirely.
    if (x.length === 0) {
      return { xMin: 0, xMax: 1, yMin: -1, yMax: 1 }
    }
    let xLo = Number.POSITIVE_INFINITY
    let xHi = Number.NEGATIVE_INFINITY
    for (let i = 0; i < x.length; i++) {
      const v = Number(x[i])
      if (!Number.isFinite(v)) continue
      if (v < xLo) xLo = v
      if (v > xHi) xHi = v
    }
    if (!Number.isFinite(xLo) || !Number.isFinite(xHi)) {
      xLo = 0
      xHi = 1
    }

    // Robust y-range — NMR spectra usually have one dominant peak (residual
    // solvent / water) that's many orders of magnitude above everything
    // else. Anchoring the upper limit to the global max squashes the useful
    // spectrum into 1 pixel of vertical space, while anchoring the lower
    // limit to 0 chops baseline/noise below zero. Robust quantiles keep the
    // typical trace visible while the dominant peak clips off the top —
    // standard NMR display behaviour.
    //
    // When the mask is active, build a copy of ``y`` that skips the masked
    // region before computing the percentile, so the y-axis is anchored to
    // the analyte signal rather than the now-invisible solvent spike.
    let baselineY: ArrayLike<number> = displaySourceY
    if (maskDominantPeak && dominantPeakRange) {
      const filtered: number[] = []
      for (let i = 0; i < displaySourceY.length; i++) {
        if (i >= dominantPeakRange.startIndex && i <= dominantPeakRange.endIndex) continue
        filtered.push(displaySourceY[i])
      }
      baselineY = filtered
    }
    // Noise σ for the baseline. Passed to ``robustSpectrumYRange`` so it
    // can clamp the visible bottom near ``-4σ`` — honest noise stays
    // visible, but big negative dispersion lobes around saturated solvent
    // / aromatic peaks fall below the frame instead of cutting through the
    // baseline. Matches the industry-standard "Only Positive" display
    // convention used by NMR-processing software.
    const baselineNoiseSigma = estimateBaselineNoiseSigma(baselineY)
    const ranges = [
      robustSpectrumYRange(baselineY, { noiseFloor: baselineNoiseSigma }),
    ]
    if (showPredicted && overlays?.predicted) {
      ranges.push(
        robustSpectrumYRange(overlays.predicted.y, {
          noiseFloor: estimateBaselineNoiseSigma(overlays.predicted.y),
        }),
      )
    }
    const yRange = combineSpectrumYRanges(ranges)

    return {
      xMin: xLo,
      xMax: xHi,
      yMin: yRange.yMin,
      yMax: yRange.yMax,
    }
  }, [x, displaySourceY, overlays, showPredicted, maskDominantPeak, dominantPeakRange])

  const [xRange, setXRange] = useState<[number, number] | null>(null)
  const plotDivRef = useRef<PlotlyGraphDivLike | null>(null)
  const dragPanRef = useRef<{
    pointerId: number
    startClientX: number
    startRange: [number, number]
    paneWidth: number
  } | null>(null)
  // Pan stabilisation. The drag writes its target range into a ref and a single
  // requestAnimationFrame commits it, so a 120 Hz+ pointer stream collapses to
  // one setXRange per frame. ``isPanning`` additionally freezes the resampled
  // trace for the duration of the drag (see ``sampleXRange`` below).
  const [isPanning, setIsPanning] = useState(false)
  const panRafRef = useRef(0)
  const panTargetRef = useRef<[number, number] | null>(null)

  const effectiveXMin = xRange ? xRange[0] : xMin
  const effectiveXMax = xRange ? xRange[1] : xMax
  const visibleXRange = useMemo<readonly [number, number] | null>(
    () => (xRange ? ([effectiveXMin, effectiveXMax] as const) : null),
    [xRange, effectiveXMin, effectiveXMax],
  )
  // Range the trace is *resampled* against. Normally the visible viewport, but
  // during an active pan it is frozen to the full span (null) so the min/max
  // envelope cannot re-pick points frame to frame — the drag becomes a pure
  // axis relayout over a fixed trace and the line stops shimmering. The precise
  // viewport-density resample is restored the instant the drag ends.
  const sampleXRange = isPanning ? null : visibleXRange
  const normalizedMaxObservedPoints = useMemo(
    () =>
      Math.max(
        MIN_VIEWPORT_TRACE_POINTS,
        Math.min(24_000, Math.round(maxObservedPoints)),
      ),
    [maxObservedPoints],
  )
  const normalizedObservedPointsPerPixel = useMemo(
    () => Math.max(1, Math.min(24, observedPointsPerPixel)),
    [observedPointsPerPixel],
  )
  const observedPointBudget = useMemo(
    () =>
      Math.max(
        MIN_VIEWPORT_TRACE_POINTS,
        Math.min(
          normalizedMaxObservedPoints,
          Math.round(plotPixelWidth * normalizedObservedPointsPerPixel),
        ),
      ),
    [plotPixelWidth, normalizedMaxObservedPoints, normalizedObservedPointsPerPixel],
  )
  const overlayPointBudget = useMemo(
    () =>
      Math.max(
        800,
        Math.min(MAX_OVERLAY_TRACE_POINTS, Math.round(plotPixelWidth * 1.35)),
      ),
    [plotPixelWidth],
  )
  const displayScale = useMemo(() => gainMultiplier(gain01) * yZoom, [gain01, yZoom])
  const observedSample = useMemo(
    () =>
      sampleSpectrumTraceForPlot(x, displaySourceY, {
        maxPoints: observedPointBudget,
        xRange: sampleXRange,
        maskRange: maskDominantPeak ? dominantPeakRange : null,
      }),
    [x, displaySourceY, observedPointBudget, sampleXRange, maskDominantPeak, dominantPeakRange],
  )
  const observedDisplayY = useMemo(
    () => Array.from(observedSample.y, (v) => scaleDisplayYValue(v, displayScale)),
    [observedSample, displayScale],
  )
  const predictedSample = useMemo(() => {
    if (!overlays?.predicted || overlays.predicted.x.length !== overlays.predicted.y.length) {
      return null
    }
    return sampleSpectrumTraceForPlot(overlays.predicted.x, overlays.predicted.y, {
      maxPoints: overlayPointBudget,
      xRange: sampleXRange,
    })
  }, [overlays, overlayPointBudget, sampleXRange])
  const displayPred = useMemo(() => {
    if (!predictedSample) return null
    return Array.from(predictedSample.y, (v) => scaleDisplayYValue(v, displayScale))
  }, [predictedSample, displayScale])
  const predictedLabel = overlays?.predicted?.label ?? "Predicted"
  const peakDisplayPoints = useMemo(
    () =>
      peaks.map((p) => ({
        ppm: p.ppm,
        y:
          p.intensity != null
            ? scaleDisplayYValue(p.intensity, displayScale)
            : scaleDisplayYValue(nearestYAtPpm(x, displaySourceY, p.ppm), displayScale),
        label: p.label ?? "",
        category: p.category ?? "unknown",
      })),
    [peaks, displayScale, x, displaySourceY],
  )
  const peakGuideShapes = useMemo(
    () =>
      showPeakGuides
        ? peakDisplayPoints
            .filter((p) => Number.isFinite(p.ppm) && Number.isFinite(p.y))
            .map((p) => ({
              type: "line",
              xref: "x",
              yref: "y",
              x0: p.ppm,
              x1: p.ppm,
              y0: 0,
              y1: p.y,
              line: { width: 1, color: "rgba(120, 120, 120, 0.45)" },
              layer: "below",
            }))
        : [],
    [peakDisplayPoints, showPeakGuides],
  )

  /**
   * Industry-standard apex ticks + rotated ppm labels.
   *
   * Standard NMR-display software draws a thin vertical "stick" above each
   * picked peak's apex and writes the chemical shift rotated 90° at the top.
   * Even when several lines of a multiplet visually merge into a single
   * envelope at the chart's zoom level (a "blob"), the row of apex ticks
   * above the trace makes the underlying line count — and therefore the
   * multiplicity — immediately obvious to the eye.
   *
   * The tick endpoints share a common ``labelRowY`` near the top of the
   * frame so the labels align in a horizontal row. ``apexClampY`` cannot
   * exceed ``labelRowY``: if a peak apex would extend above the row (e.g.
   * a clipped residual solvent spike), the tick collapses to zero length
   * and the label sits next to the apex instead.
   */
  const peakApexLabelLayout = useMemo(() => {
    if (!showPeakGuides || peakDisplayPoints.length === 0) {
      return { shapes: [] as object[], annotations: [] as object[] }
    }
    if (!Number.isFinite(yMin) || !Number.isFinite(yMax) || yMax <= yMin) {
      return { shapes: [] as object[], annotations: [] as object[] }
    }
    const span = yMax - yMin
    // Label row at ~92% of the visible height; ticks are short enough that
    // ppm labels never collide with the chart's title or top frame.
    const labelRowY = yMin + span * 0.92
    const shapes: object[] = []
    const annotations: object[] = []
    for (const peak of peakDisplayPoints) {
      if (!Number.isFinite(peak.ppm) || !Number.isFinite(peak.y)) continue
      const color =
        peak.category === "unknown"
          ? PEAK_CATEGORY_DEFAULT_COLOR
          : plotColorForCategory(peak.category)
      const apexClampY = Math.min(peak.y, labelRowY)
      shapes.push({
        type: "line",
        xref: "x",
        yref: "y",
        x0: peak.ppm,
        x1: peak.ppm,
        y0: apexClampY,
        y1: labelRowY,
        line: { width: 1.1, color },
        layer: "above",
      })
      annotations.push({
        xref: "x",
        yref: "y",
        x: peak.ppm,
        y: labelRowY,
        text: peak.ppm.toFixed(2),
        textangle: -90,
        showarrow: false,
        xanchor: "center",
        yanchor: "bottom",
        font: { size: 10, color },
      })
    }
    return { shapes, annotations }
  }, [peakDisplayPoints, showPeakGuides, yMin, yMax])

  /**
   * Plotly data traces. Three potential layers:
   *  - Observed line (always)
   *  - Predicted overlay (when an ``overlays.predicted`` payload is passed)
   *  - Peak markers (when peak annotations exist and the user hasn't hidden them)
   *    Peak guide/drop-lines are layout shapes, not data traces, so Plotly's
   *    trace-index diff stays stable even when peak annotations change.
   *
   * Critical for non-shaky rendering:
   *  - Trace type defaults to SVG ``scatter`` because processed spectra are
   *    already downsampled before Plotly sees them. Raw FID can opt into
   *    ``scattergl`` for dense FFT traces without changing the processed path.
   *  - The observed / predicted arrays are viewport-limited with a
   *    MinMaxLTTB envelope before Plotly sees them, preserving narrow peaks
   *    without forcing WebGL to diff a million-point trace on each React commit.
   *  - ``observedDisplayY`` is already gain-scaled AND mask-aware (NaN values
   *    where the dominant solvent peak should be hidden); Plotly draws NaN as a gap.
   *  - The array references are stabilised by the upstream ``useMemo`` chain,
   *    so Plotly's reactivity (driven by reference equality on ``data``) does
   *    not redraw unless the actual numeric content changed.
   */
  const data = useMemo(() => {
    if (observedSample.x.length === 0) return []
    const lineTraceType = renderMode === "webgl" ? "scattergl" : "scatter"
    const traces: object[] = [
      {
        type: lineTraceType,
        mode: "lines",
        x: observedSample.x,
        y: observedDisplayY,
        name: traceNameWithResampling("Observed", observedSample),
        line: { width: 1.2, color: "#2563eb" },
        connectgaps: false, // honour the mask's NaN holes
        hovertemplate: "δ %{x:.3f} ppm<br>I = %{y:.2e}<extra></extra>",
      },
    ]
    if (
      showPredicted &&
      predictedSample &&
      displayPred
    ) {
      traces.push({
        type: lineTraceType,
        mode: "lines",
        x: predictedSample.x,
        y: displayPred,
        name: traceNameWithResampling(predictedLabel, predictedSample),
        line: { width: 1, dash: "dash", color: "#c026d3" },
        opacity: 0.85,
        connectgaps: false,
      })
    }
    if (showPeaks && peakDisplayPoints.length > 0) {
      // Group peaks by category so each category renders as its own colored
      // scatter trace — gives the user a one-glance grouping (aromatic vs
      // aliphatic vs labile) AND a working legend they can toggle.
      // Peaks without a category fall through to the default orange.
      type Bucket = { px: number[]; py: number[]; labels: string[] }
      const byCategory = new Map<string, Bucket>()
      for (const peak of peakDisplayPoints) {
        const cat = peak.category
        const bucket = byCategory.get(cat) ?? { px: [], py: [], labels: [] }
        bucket.px.push(peak.ppm)
        bucket.py.push(peak.y)
        bucket.labels.push(peak.label)
        byCategory.set(cat, bucket)
      }
      // Render in a stable order so the legend doesn't reshuffle on every
      // re-render (Plotly's diff is reference-stable so order matters).
      const orderedCategories = Array.from(byCategory.keys()).sort()
      for (const cat of orderedCategories) {
        const bucket = byCategory.get(cat)
        if (!bucket) continue
        const color =
          cat === "unknown"
            ? PEAK_CATEGORY_DEFAULT_COLOR
            : plotColorForCategory(cat)
        traces.push({
          type: "scatter",
          // ``markers`` only: the per-peak ppm labels live in layout
          // annotations (industry-standard rotated stick labels, see
          // ``peakApexLabelLayout`` above) so they survive Plotly's
          // marker-overlap collision avoidance and align in a horizontal
          // row across the top of the frame. The full multiplicity label
          // (e.g. "7.46 (s, 3H)") still appears in the hover tooltip via
          // ``hovertext``.
          mode: "markers",
          x: bucket.px,
          y: bucket.py,
          hovertext: bucket.labels,
          name: humanizePeakCategory(cat),
          marker: { size: 7, color, line: { width: 0.5, color: "#fff" } },
          hovertemplate: "δ %{x:.3f} ppm<br>I = %{y:.2e}<br>%{hovertext}<extra></extra>",
        })
      }
    }
    return traces
  }, [
    observedSample,
    observedDisplayY,
    displayPred,
    predictedSample,
    predictedLabel,
    peakDisplayPoints,
    renderMode,
    showPeaks,
    showPredicted,
  ])

  /**
   * Plotly layout. Two NMR-display anti-shake rules implemented here:
   *
   *   1. ``uirevision: "spectrum"`` — Plotly keeps pan/zoom/drag state
   *      across data updates instead of resetting to autorange every
   *      time. (Standard mouse-scroll behavior.)
   *   2. Y-axis ``range`` is anchored to a stable robust source-data range
   *      with bottom padding. Gain/yZoom ticks therefore do NOT change the
   *      axis range, only ``data`` trace values and lightweight guide-line
   *      shapes — i.e. "vertical-zoom does NOT re-trigger Fit to height"
   *      (industry-standard NMR-display behavior).
   *
   * Layout deps deliberately depend on primitives plus the precomputed
   * shape overlay, so a sibling re-render that hands us a fresh-but-equal
   * ``overlays`` object reference doesn't invalidate the layout and trigger
   * a Plotly redraw.
   */
  const hasPredictedOverlay = Boolean(overlays?.predicted && showPredicted)
  const hasPeakMarkers = showPeaks && peaks.length > 0
  const layout = useMemo(
    () => ({
      autosize: true,
      margin: PLOT_MARGIN,
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      showlegend: hasPredictedOverlay || hasPeakMarkers,
      // Plotly is staticPlot:true so dragmode is moot — but explicitly
      // setting ``false`` ensures no listener attach/detach happens even
      // if a future refactor flips staticPlot off.
      dragmode: false,
      xaxis: {
        title: xLabel,
        // Always an explicit range — never Plotly autorange. Autorange pads
        // the data span by a few percent, which (a) is not standard NMR
        // display (spectra fill the frame edge-to-edge) and (b) would make
        // the cursor→ppm mapping used by the hover readout disagree with
        // where Plotly actually drew each point. effectiveXMin/effectiveXMax
        // already fall back to the full data span when the user has not
        // zoomed, so this stays correct in every view.
        autorange: false as const,
        range: reversedXAxis
          ? [effectiveXMax, effectiveXMin]
          : [effectiveXMin, effectiveXMax],
        zeroline: false,
        showgrid: false,
        fixedrange: true,
      },
      yaxis: {
        title: yLabel,
        // Anchored to the robust source range — the baseline stays visible
        // instead of being clipped at y=0, and dominant solvent peaks can
        // still clip at the top like a standard NMR display.
        range: [yMin, yMax],
        zeroline: true,
        zerolinecolor: "rgba(100, 116, 139, 0.45)",
        zerolinewidth: 1,
        showgrid: false,
        fixedrange: true,
      },
      // Hover crosshair OFF — every mouse move was firing Plotly's hover
      // detector, which on dense traces (>10 k points) re-painted the
      // overlay each frame. That was the visible flicker.
      hovermode: false,
      // Layout shapes = (a) drop-line guides from baseline up to each apex
      // and (b) industry-standard apex ticks from each apex up to the common
      // label row near the top of the frame. The drop-line gives the eye a
      // direct mapping from peak → ppm axis; the apex tick + rotated label
      // makes the multiplicity readable at any zoom level.
      shapes: [...peakGuideShapes, ...peakApexLabelLayout.shapes],
      annotations: peakApexLabelLayout.annotations,
      transition: { duration: 0 },
      uirevision: "spectrum",
    }),
    [
      xLabel,
      yLabel,
      reversedXAxis,
      xRange,
      effectiveXMin,
      effectiveXMax,
      yMin,
      yMax,
      hasPredictedOverlay,
      hasPeakMarkers,
      peakGuideShapes,
      peakApexLabelLayout,
    ],
  )

  const rememberPlotlyGraphDiv = useCallback((_figure: unknown, graphDiv: unknown) => {
    plotDivRef.current = (graphDiv as PlotlyGraphDivLike | null) ?? null
  }, [])

  /**
   * Full reset — restores every interactive setting to its first-preview state:
   *   • xRange   → null (Plotly autorange shows the full data span)
   *   • yZoom    → 1× (no peak height bumping)
   *   • gain01   → 0 (multiplier 1×; whole spectrum fits inside the y-axis)
   *   • peak overlays/guides → initial defaults for this viewer
   * Both "Reset zoom" and "Full spectrum" route through this so they always
   * restore the exact view the user saw on first preview.
   */
  const resetAll = useCallback(() => {
    setXRange(null)
    setYZoom(1)
    setGain01(0)
    setShowPeaks(defaultShowPeaks)
    setShowPeakGuides(defaultShowPeakGuides)
  }, [defaultShowPeakGuides, defaultShowPeaks])

  const resetZoom = resetAll
  const fullSpectrum = resetAll

  const pan = useCallback(
    (dir: "left" | "right") => {
      const span = effectiveXMax - effectiveXMin || 1
      const step = span * 0.08
      const delta = dir === "left" ? -step : step
      setXRange([effectiveXMin + delta, effectiveXMax + delta])
    },
    [effectiveXMin, effectiveXMax]
  )

  const clampRangeToDomain = useCallback(
    (range: [number, number]): [number, number] => {
      const domainLo = Math.min(xMin, xMax)
      const domainHi = Math.max(xMin, xMax)
      const domainSpan = domainHi - domainLo
      const span = range[1] - range[0]
      if (domainSpan <= 0 || span <= 0 || span >= domainSpan) return range
      if (range[0] < domainLo) return [domainLo, domainLo + span]
      if (range[1] > domainHi) return [domainHi - span, domainHi]
      return range
    },
    [xMin, xMax],
  )

  const startMoveDrag = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!moveMode || e.button !== 0) return
      e.preventDefault()
      const pane = e.currentTarget
      dragPanRef.current = {
        pointerId: e.pointerId,
        startClientX: e.clientX,
        startRange: [effectiveXMin, effectiveXMax],
        paneWidth: Math.max(pane.getBoundingClientRect().width, 1),
      }
      panTargetRef.current = null
      setIsPanning(true)
      try {
        pane.setPointerCapture(e.pointerId)
      } catch {
        // Synthetic PointerEvents in tests/devtools may not register as
        // active browser pointers. The drag state above is enough for the
        // React move handler; real user pointers still get capture.
      }
    },
    [moveMode, effectiveXMin, effectiveXMax],
  )

  const moveDrag = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      const drag = dragPanRef.current
      if (!drag || drag.pointerId !== e.pointerId) return
      e.preventDefault()
      const span = drag.startRange[1] - drag.startRange[0] || 1
      const pixels = e.clientX - drag.startClientX
      const direction = reversedXAxis ? 1 : -1
      const delta = direction * (pixels / drag.paneWidth) * span
      panTargetRef.current = clampRangeToDomain([
        drag.startRange[0] + delta,
        drag.startRange[1] + delta,
      ])
      // Coalesce range updates to one per animation frame. Pointermove fires
      // faster than the display refresh (120 Hz+ on many trackpads/mice); an
      // unthrottled setXRange per event was a source of the pan judder.
      if (!panRafRef.current) {
        panRafRef.current = window.requestAnimationFrame(() => {
          panRafRef.current = 0
          if (panTargetRef.current) setXRange(panTargetRef.current)
        })
      }
    },
    [clampRangeToDomain, reversedXAxis],
  )

  const endMoveDrag = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragPanRef.current
    if (!drag || drag.pointerId !== e.pointerId) return
    dragPanRef.current = null
    // Flush any range update still queued for the next frame, then unfreeze
    // the trace so the precise viewport-density resample is restored.
    if (panRafRef.current) {
      window.cancelAnimationFrame(panRafRef.current)
      panRafRef.current = 0
    }
    if (panTargetRef.current) {
      setXRange(panTargetRef.current)
      panTargetRef.current = null
    }
    setIsPanning(false)
    try {
      e.currentTarget.releasePointerCapture(e.pointerId)
    } catch {
      // See setPointerCapture guard in startMoveDrag.
    }
  }, [])

  // ── Custom hover readout ────────────────────────────────────────────────
  // Plotly is left fully static (``hovermode:false``, ``staticPlot:true``):
  // re-enabling Plotly's own hover repainted the overlay on every mouse move
  // and was the historical flicker source. Instead the cursor is mapped to a
  // ppm here using the same plot margins and x-axis range Plotly renders,
  // then surfaced through a lightweight absolutely-positioned overlay.
  // Because this never mutates Plotly's ``data``/``layout`` props, Plotly
  // never redraws — the chart stays perfectly stable while the readout
  // tracks the cursor.
  const hoverRafRef = useRef(0)
  const hoverPointerRef = useRef<{
    width: number
    height: number
    px: number
    py: number
  } | null>(null)

  const clearHoverReadout = useCallback(() => {
    hoverPointerRef.current = null
    if (hoverRafRef.current) {
      window.cancelAnimationFrame(hoverRafRef.current)
      hoverRafRef.current = 0
    }
    setHoverReadout((current) => (current ? null : current))
  }, [])

  const recomputeHover = useCallback(() => {
    hoverRafRef.current = 0
    if (contextMenuOpen) {
      clearHoverReadout()
      return
    }
    const pointer = hoverPointerRef.current
    if (!pointer) return
    const { width, height, px, py } = pointer
    const fullLayout = plotDivRef.current?._fullLayout
    const [plotLeft, plotRight] = axisPixelBounds(fullLayout?.xaxis, PLOT_MARGIN.l, width - PLOT_MARGIN.r)
    const [plotTop, plotBottom] = axisPixelBounds(fullLayout?.yaxis, PLOT_MARGIN.t, height - PLOT_MARGIN.b)
    if (
      plotRight - plotLeft <= 1 ||
      plotBottom - plotTop <= 1 ||
      px < plotLeft ||
      px > plotRight ||
      py < plotTop ||
      py > plotBottom ||
      x.length === 0 ||
      displaySourceY.length === 0
    ) {
      setHoverReadout((current) => (current ? null : current))
      return
    }
    const shift = chemicalShiftFromPlotPointer({
      pointerX: px,
      paneWidth: width,
      effectiveXMin,
      effectiveXMax,
      reversedXAxis,
      plotlyXAxis: fullLayout?.xaxis,
    })
    if (!shift) {
      setHoverReadout((current) => (current ? null : current))
      return
    }
    const nearestPoint = nearestSourcePointAtPpm(
      x,
      displaySourceY,
      shift.ppm,
      maskDominantPeak ? dominantPeakRange : null,
    )
    setHoverReadout({
      crosshairLeft: shift.crosshairLeft,
      plotTop,
      plotBottom,
      paneWidth: width,
      ppm: shift.ppm,
      intensity: nearestPoint?.intensity ?? Number.NaN,
    })
  }, [
    x,
    displaySourceY,
    effectiveXMin,
    effectiveXMax,
    reversedXAxis,
    maskDominantPeak,
    dominantPeakRange,
    contextMenuOpen,
    clearHoverReadout,
  ])

  const handleChartPointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      moveDrag(e)
      if (contextMenuOpen) {
        clearHoverReadout()
        return
      }
      // While actively panning, hide the readout — the crosshair would fight
      // the drag and the values are sliding under the cursor anyway.
      if (dragPanRef.current) {
        clearHoverReadout()
        return
      }
      const rect = e.currentTarget.getBoundingClientRect()
      hoverPointerRef.current = {
        width: rect.width,
        height: rect.height,
        px: e.clientX - rect.left,
        py: e.clientY - rect.top,
      }
      // Coalesce to one readout update per animation frame.
      if (!hoverRafRef.current) {
        hoverRafRef.current = window.requestAnimationFrame(recomputeHover)
      }
    },
    [moveDrag, contextMenuOpen, clearHoverReadout, recomputeHover],
  )

  const handleChartPointerLeave = useCallback(() => {
    clearHoverReadout()
  }, [clearHoverReadout])

  const openSpectrumContextMenu = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      event.preventDefault()
      event.stopPropagation()
      clearHoverReadout()
      setContextMenuPosition(clampSpectrumContextMenuPosition(event.clientX, event.clientY))
    },
    [clearHoverReadout],
  )

  const closeSpectrumContextMenu = useCallback(() => {
    setContextMenuPosition(null)
  }, [])

  useEffect(() => {
    if (!contextMenuOpen) return
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target
      if (target instanceof Node && contextMenuRef.current?.contains(target)) return
      closeSpectrumContextMenu()
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeSpectrumContextMenu()
    }
    document.addEventListener("pointerdown", handlePointerDown, true)
    document.addEventListener("keydown", handleKeyDown, true)
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown, true)
      document.removeEventListener("keydown", handleKeyDown, true)
    }
  }, [closeSpectrumContextMenu, contextMenuOpen])

  useEffect(() => {
    if (!contextMenuOpen || !contextMenuPosition || !contextMenuRef.current) return
    const rect = contextMenuRef.current.getBoundingClientRect()
    const next = clampSpectrumContextMenuPosition(
      contextMenuPosition.x,
      contextMenuPosition.y,
      rect.width,
      rect.height,
    )
    if (
      Math.abs(next.x - contextMenuPosition.x) > 0.5 ||
      Math.abs(next.y - contextMenuPosition.y) > 0.5
    ) {
      setContextMenuPosition(next)
    }
  }, [contextMenuOpen, contextMenuPosition])

  useEffect(
    () => () => {
      if (hoverRafRef.current) window.cancelAnimationFrame(hoverRafRef.current)
      if (panRafRef.current) window.cancelAnimationFrame(panRafRef.current)
    },
    [],
  )

  const bumpPeakHeight = useCallback((sign: 1 | -1) => {
    setYZoom((z) => {
      const next = z * (sign === 1 ? 1.12 : 1 / 1.12)
      return Math.min(Math.max(next, 0.25), 20)
    })
  }, [])

  /** X-axis zoom in/out — narrows or widens the visible range around its center. */
  const zoom = useCallback(
    (dir: "in" | "out") => {
      const span = effectiveXMax - effectiveXMin || 1
      const center = (effectiveXMin + effectiveXMax) / 2
      const nextSpan = dir === "in" ? span * 0.7 : span * 1.4
      setXRange([center - nextSpan / 2, center + nextSpan / 2])
    },
    [effectiveXMin, effectiveXMax],
  )

  // ── Non-passive wheel handler for the gain rail ─────────────────────────
  // React's onWheel is passive by default in modern browsers, so calling
  // preventDefault inside it is silently ignored and the page scrolls anyway.
  // Attach a native non-passive listener so wheel scrolling on the rail
  // adjusts gain WITHOUT scrolling the surrounding page.
  const gainRailRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const el = gainRailRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      e.stopPropagation()
      const delta = -e.deltaY * 0.0008
      setGain01((g) => Math.min(1, Math.max(0, g + delta)))
    }
    el.addEventListener("wheel", onWheel, { passive: false })
    return () => el.removeEventListener("wheel", onWheel)
  }, [])

  const placeholder = x.length === 0 || y.length === 0 || x.length !== y.length

  if (placeholder) {
    return (
      <div
        className={cn(
          "flex min-h-[280px] flex-col items-center justify-center rounded-lg border border-dashed bg-muted/30 p-8 text-center text-sm text-muted-foreground",
          className
        )}
      >
        <Layers className="mb-2 h-8 w-8 opacity-40" aria-hidden />
        <p className="font-medium text-foreground">No spectrum loaded</p>
        <p className="mt-1 max-w-md">
          Upload and preview/process on the server to plot ppm vs intensity ({nucleus ?? "1H/13C"}). Display gain only
          scales rendering — source arrays are never modified.
        </p>
      </div>
    )
  }

  return (
    <div className={cn("flex flex-col gap-3", className)} aria-label={`${nucleus ?? "NMR"} spectrum display`}>
      {nucleus && (
        <p className="text-xs text-muted-foreground">
          Nucleus context: <span className="font-mono font-medium text-foreground">{nucleus}</span>
        </p>
      )}

      {/*
        Spectrum container (compact by default). flex-col so the chart fills
        the top and the controls dock at the bottom. Keep this as a normal
        document-flow box: forcing a compositor layer with transform/
        containment made the large analysis card disappear/reappear during
        scroll on some browsers.
      */}
      <div
        className={cn(
          "group flex w-full min-w-0 flex-col overflow-hidden rounded-lg border bg-card",
          expanded ? "h-[min(640px,70vh)]" : "h-[360px]",
        )}
      >
        {/*
          Chart pane — fills the available container height. The context menu
          is opened from capture phase so Plotly's internal layers cannot
          swallow the right-click before SpectrumViewer sees it.
        */}
        <div
          ref={chartPaneRef}
          className={cn(
            "relative min-h-0 flex-1",
            moveMode ? "cursor-grab active:cursor-grabbing" : "cursor-crosshair",
          )}
          data-testid="spectrum-move-pane"
          onContextMenuCapture={openSpectrumContextMenu}
          onPointerDown={startMoveDrag}
          onPointerMove={handleChartPointerMove}
          onPointerUp={endMoveDrag}
          onPointerCancel={endMoveDrag}
          onPointerLeave={handleChartPointerLeave}
          style={{ touchAction: moveMode ? "none" : "pan-y" }}
        >
          <Plot
            data={data}
            layout={layout}
            config={{
              // Plotly is in fully-static mode here: every interaction
              // (hover, scroll-wheel zoom, box-zoom, double-click reset,
              // drag) is driven by our own toolbar buttons, which call
              // setXRange/setGain01/etc. and let React update layout/data
              // through Plotly's diff. That removes Plotly's listener
              // attach/detach overhead — the single biggest remaining
              // source of flicker.
              displayModeBar: false,
              displaylogo: false,
              // ``responsive: true`` and ``useResizeHandler`` BOTH attach
              // window-resize listeners and call ``Plotly.Plots.resize()``.
              // Running them together caused a double-resize on every
              // viewport change — and on every layout shift below the
              // chart (e.g. evidence panels mounting after analyze lands)
              // Plotly's internal ResizeObserver also fires. Keeping only
              // ``useResizeHandler`` means the chart resizes when its own
              // container changes size, not when an unrelated sibling
              // mutates the DOM below it. (NMR-display anti-shake convention.)
              responsive: false,
              scrollZoom: false,
              staticPlot: true,
            }}
            style={{ width: "100%", height: "100%" }}
            useResizeHandler
            onInitialized={rememberPlotlyGraphDiv}
            onUpdate={rememberPlotlyGraphDiv}
          />

          {/*
            Custom hover overlay — a Plotly-free crosshair + chemical-shift
            readout. Rendered as plain absolutely-positioned divs so it never
            triggers a Plotly redraw (the chart stays stable). ``pointer-events
            -none`` keeps the pane's own pan/hover pointer handlers working.
          */}
          {hoverReadout ? (
            <div className="pointer-events-none absolute inset-0 z-10">
              <div
                className="absolute w-px bg-sky-500/70"
                style={{
                  left: hoverReadout.crosshairLeft,
                  top: hoverReadout.plotTop,
                  height: Math.max(0, hoverReadout.plotBottom - hoverReadout.plotTop),
                }}
              />
              <div
                role="status"
                aria-live="polite"
                className="absolute rounded-md border bg-popover/95 px-2 py-1 font-mono text-[11px] leading-tight shadow-sm"
                style={{
                  top: hoverReadout.plotTop + 4,
                  ...(hoverReadout.crosshairLeft > hoverReadout.paneWidth / 2
                    ? { right: hoverReadout.paneWidth - hoverReadout.crosshairLeft + 6 }
                    : { left: hoverReadout.crosshairLeft + 6 }),
                }}
              >
                <div className="font-semibold tabular-nums text-foreground">
                  δ {hoverReadout.ppm.toFixed(3)} ppm
                </div>
                <div className="tabular-nums text-muted-foreground">
                  {Number.isFinite(hoverReadout.intensity)
                    ? `I ${hoverReadout.intensity.toExponential(2)}`
                    : "I —"}
                </div>
              </div>
            </div>
          ) : null}
        </div>
        {contextMenuPosition ? (
          <div
            ref={contextMenuRef}
            role="menu"
            aria-label="Spectrum"
            className="fixed z-50 w-60 overflow-y-auto rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
            style={{
              left: contextMenuPosition.x,
              top: contextMenuPosition.y,
              maxHeight: spectrumContextMenuMaxHeight(),
            }}
            onContextMenu={(event) => {
              event.preventDefault()
              event.stopPropagation()
            }}
          >
            <div className="px-2 py-1.5 text-sm font-medium text-foreground">Spectrum</div>
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center rounded-sm px-2 py-1.5 text-left text-sm outline-none hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground"
              onClick={() => { zoom("in"); closeSpectrumContextMenu() }}
            >
              Zoom in
            </button>
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center rounded-sm px-2 py-1.5 text-left text-sm outline-none hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground"
              onClick={() => { zoom("out"); closeSpectrumContextMenu() }}
            >
              Zoom out
            </button>
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center rounded-sm px-2 py-1.5 text-left text-sm outline-none hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground"
              onClick={() => { fullSpectrum(); closeSpectrumContextMenu() }}
            >
              Full spectrum
            </button>
            <div className="-mx-1 my-1 h-px bg-border" />
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center rounded-sm px-2 py-1.5 text-left text-sm outline-none hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground"
              onClick={() => { pan("left"); closeSpectrumContextMenu() }}
            >
              Pan left
            </button>
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center rounded-sm px-2 py-1.5 text-left text-sm outline-none hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground"
              onClick={() => { pan("right"); closeSpectrumContextMenu() }}
            >
              Pan right
            </button>
            <div className="-mx-1 my-1 h-px bg-border" />
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center rounded-sm px-2 py-1.5 text-left text-sm outline-none hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground"
              onClick={() => bumpPeakHeight(1)}
            >
              Taller peaks
            </button>
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center rounded-sm px-2 py-1.5 text-left text-sm outline-none hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground"
              onClick={() => bumpPeakHeight(-1)}
            >
              Shorter peaks
            </button>
            <div className="-mx-1 my-1 h-px bg-border" />
            <button
              type="button"
              role="menuitemcheckbox"
              aria-checked={showPeaks}
              className="flex w-full items-center gap-2 rounded-sm py-1.5 pr-2 pl-2 text-left text-sm outline-none hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground"
              onClick={() => setShowPeaks((value) => !value)}
            >
              <span className="flex size-4 shrink-0 items-center justify-center" aria-hidden>
                {showPeaks ? <Check className="size-4" /> : null}
              </span>
              Peak markers and legend
            </button>
            {peaks.length > 0 ? (
              <button
                type="button"
                role="menuitemcheckbox"
                aria-checked={showPeakGuides}
                className="flex w-full items-center gap-2 rounded-sm py-1.5 pr-2 pl-2 text-left text-sm outline-none hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground"
                onClick={() => setShowPeakGuides((value) => !value)}
              >
                <span className="flex size-4 shrink-0 items-center justify-center" aria-hidden>
                  {showPeakGuides ? <Check className="size-4" /> : null}
                </span>
                Vertical peak guides
              </button>
            ) : null}
            {overlays?.predicted ? (
              <button
                type="button"
                role="menuitemcheckbox"
                aria-checked={showPredicted}
                className="flex w-full items-center gap-2 rounded-sm py-1.5 pr-2 pl-2 text-left text-sm outline-none hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground"
                onClick={() => setShowPredicted((value) => !value)}
              >
                <span className="flex size-4 shrink-0 items-center justify-center" aria-hidden>
                  {showPredicted ? <Check className="size-4" /> : null}
                </span>
                Predicted overlay
              </button>
            ) : null}
            {dominantPeakRange ? (
              <button
                type="button"
                role="menuitemcheckbox"
                aria-checked={maskDominantPeak}
                className="flex w-full items-center gap-2 rounded-sm py-1.5 pr-2 pl-2 text-left text-sm outline-none hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground"
                onClick={() => setMaskDominantPeak((value) => !value)}
              >
                <span className="flex size-4 shrink-0 items-center justify-center" aria-hidden>
                  {maskDominantPeak ? <Check className="size-4" /> : null}
                </span>
                Mask solvent peak
              </button>
            ) : null}
            <button
              type="button"
              role="menuitemcheckbox"
              aria-checked={expanded}
              className="flex w-full items-center gap-2 rounded-sm py-1.5 pr-2 pl-2 text-left text-sm outline-none hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground"
              onClick={() => setExpanded((value) => !value)}
            >
              <span className="flex size-4 shrink-0 items-center justify-center" aria-hidden>
                {expanded ? <Check className="size-4" /> : null}
              </span>
              Expanded view
            </button>
            <div className="-mx-1 my-1 h-px bg-border" />
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center rounded-sm px-2 py-1.5 text-left text-sm outline-none hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground"
              onClick={() => { resetZoom(); closeSpectrumContextMenu() }}
            >
              Reset axes
            </button>
          </div>
        ) : null}

        {/*
          Bottom controls bar — replaces the previous floating draggable
          toolbar + vertical gain rail. Pinned to the bottom of the chart
          container so it never overlaps the spectrum, never moves during
          interaction, and never triggers an opacity-transition repaint.
        */}
        <div className="shrink-0 border-t bg-card/95 px-3 py-2">
          <div className="flex flex-wrap items-center gap-3">
            {/* Gain — horizontal slider replaces the old vertical rail. */}
            <div ref={gainRailRef} className="flex min-w-[180px] flex-1 items-center gap-2">
              <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                Gain
              </span>
              <Slider
                value={[gain01 * 100]}
                min={0}
                max={100}
                step={0.5}
                onValueChange={(v) => setGain01((v[0] ?? 0) / 100)}
                className="flex-1"
                aria-label="Intensity gain (display only)"
              />
              <span
                className="font-mono text-[10px] tabular-nums text-muted-foreground"
                title={`Total scale = gain × yZoom. yZoom=${yZoom.toFixed(2)}`}
              >
                ×{(gainMultiplier(gain01) * yZoom).toExponential(1)}
              </span>
            </div>

            {/* Button row — every interaction is React-side; Plotly is static. */}
            <div className="ml-auto flex flex-wrap items-center gap-1">
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-7 w-7"
                onClick={fullSpectrum}
                title="Full spectrum (reset to first-preview view)"
              >
                <Expand className="h-3.5 w-3.5" aria-hidden />
                <span className="sr-only">Full spectrum</span>
              </Button>
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-7 w-7"
                onClick={() => zoom("in")}
                title="Zoom in (x-axis)"
              >
                <ZoomIn className="h-3.5 w-3.5" aria-hidden />
                <span className="sr-only">Zoom in</span>
              </Button>
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-7 w-7"
                onClick={() => zoom("out")}
                title="Zoom out (x-axis)"
              >
                <ZoomOut className="h-3.5 w-3.5" aria-hidden />
                <span className="sr-only">Zoom out</span>
              </Button>
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-7 w-7"
                onClick={() => pan("left")}
                title="Pan left"
              >
                <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
                <span className="sr-only">Pan left</span>
              </Button>
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-7 w-7"
                onClick={() => pan("right")}
                title="Pan right"
              >
                <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                <span className="sr-only">Pan right</span>
              </Button>
              <Button
                type="button"
                variant={moveMode ? "secondary" : "outline"}
                size="icon"
                className="h-7 w-7"
                onClick={() => setMoveMode((v) => !v)}
                title={moveMode ? "Move mode on — drag inside the spectrum to pan" : "Move spectrum"}
                aria-pressed={moveMode}
              >
                <Hand className="h-3.5 w-3.5" aria-hidden />
                <span className="sr-only">
                  {moveMode ? "Disable spectrum move mode" : "Move spectrum"}
                </span>
              </Button>
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-7 w-7"
                onClick={() => bumpPeakHeight(1)}
                title="Taller peaks"
              >
                <Plus className="h-3.5 w-3.5" aria-hidden />
                <span className="sr-only">Taller peaks</span>
              </Button>
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-7 w-7"
                onClick={() => bumpPeakHeight(-1)}
                title="Shorter peaks"
              >
                <Minus className="h-3.5 w-3.5" aria-hidden />
                <span className="sr-only">Shorter peaks</span>
              </Button>
              <Button
                type="button"
                variant={showPeaks ? "secondary" : "outline"}
                size="icon"
                className="h-7 w-7"
                onClick={() => setShowPeaks((v) => !v)}
                title={showPeaks ? "Hide peak markers and legend" : "Show peak markers and legend"}
                aria-pressed={showPeaks}
              >
                {showPeaks ? (
                  <Eye className="h-3.5 w-3.5" aria-hidden />
                ) : (
                  <EyeOff className="h-3.5 w-3.5" aria-hidden />
                )}
                <span className="sr-only">
                  {showPeaks ? "Hide" : "Show"} peak markers and legend
                </span>
              </Button>
              {overlays?.predicted ? (
                <Button
                  type="button"
                  variant={showPredicted ? "secondary" : "outline"}
                  size="icon"
                  className="h-7 w-7"
                  onClick={() => setShowPredicted((v) => !v)}
                  title={showPredicted ? "Hide predicted overlay" : "Show predicted overlay"}
                >
                  <Layers className="h-3.5 w-3.5" aria-hidden />
                  <span className="sr-only">
                    {showPredicted ? "Hide" : "Show"} predicted overlay
                  </span>
                </Button>
              ) : null}
              {dominantPeakRange ? (
                <Button
                  type="button"
                  variant={maskDominantPeak ? "secondary" : "outline"}
                  size="icon"
                  className="h-7 w-7"
                  onClick={() => setMaskDominantPeak((v) => !v)}
                  title={
                    maskDominantPeak
                      ? `Solvent peak at ~${dominantPeakRange.centerPpm.toFixed(2)} ppm is masked. Click to show it.`
                      : `Solvent peak detected at ~${dominantPeakRange.centerPpm.toFixed(2)} ppm. Click to mask it.`
                  }
                  aria-pressed={maskDominantPeak}
                >
                  <Droplets className="h-3.5 w-3.5" aria-hidden />
                  <span className="sr-only">
                    {maskDominantPeak ? "Show" : "Hide"} solvent peak at {dominantPeakRange.centerPpm.toFixed(2)} ppm
                  </span>
                </Button>
              ) : null}
              <Button
                type="button"
                variant={expanded ? "secondary" : "outline"}
                size="icon"
                className="h-7 w-7"
                onClick={() => setExpanded((v) => !v)}
                title={expanded ? "Collapse to compact view" : "Expand to full view"}
                aria-pressed={expanded}
              >
                {expanded ? (
                  <Minimize2 className="h-3.5 w-3.5" aria-hidden />
                ) : (
                  <Maximize2 className="h-3.5 w-3.5" aria-hidden />
                )}
                <span className="sr-only">
                  {expanded ? "Collapse spectrum" : "Expand spectrum"}
                </span>
              </Button>
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-7 w-7"
                onClick={resetZoom}
                title="Reset axes"
              >
                <RotateCcw className="h-3.5 w-3.5" aria-hidden />
                <span className="sr-only">Reset axes</span>
              </Button>
            </div>
          </div>
        </div>

      </div>
    </div>
  )
}

/**
 * Public, memoised export. Wrapping the implementation in ``React.memo``
 * short-circuits the entire viewer when its props (x, y, peaks, overlays,
 * …) are referentially equal. Combined with the caller-side ``useMemo``
 * wrapping of every extracted array, sibling state churn (sample-id
 * keystrokes, autosave ticks) becomes invisible to the chart.
 */
export const SpectrumViewer = memo(SpectrumViewerImpl)
