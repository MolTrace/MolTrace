"use client"

/**
 * Canvas-based NMR spectrum renderer (uPlot).
 *
 * This is the Step 5 swap from the spectrum-stabilization plan: uPlot draws
 * 100k+ points at 60 fps on a single ``<canvas>`` element. The component is
 * wrapped in :func:`React.memo` so a parent re-render that doesn't change
 * ``data`` or ``options`` is a no-op. The chart instance is created exactly
 * once on mount; subsequent ``data``/``range`` updates flow through
 * ``setData`` / ``setScale``, which are constant-time and bypass React.
 *
 * Why we don't import uPlot statically: it touches ``window`` at module
 * load time. Pulling it in as a top-level import would crash SSR; the
 * dynamic loader keeps the SSR-rendered shell harmless and only resolves
 * uPlot once the browser is alive.
 */

import React, { memo, useEffect, useMemo, useRef } from "react"
import type uPlotType from "uplot"
import type { AlignedData, Options } from "uplot"
import { rafThrottle } from "@/src/lib/spectracheck/raf-throttle"
// uPlot CSS — must be present for the chart to lay out correctly.
import "uplot/dist/uPlot.min.css"

// Lazy module handle so SSR doesn't import the canvas-touching code.
type UPlotCtor = typeof uPlotType
let uPlotPromise: Promise<UPlotCtor> | null = null
function loadUPlot(): Promise<UPlotCtor> {
  if (uPlotPromise) return uPlotPromise
  uPlotPromise = import("uplot").then((m) => m.default as UPlotCtor)
  return uPlotPromise
}

export type UPlotPeak = {
  ppm: number
  intensity?: number
  label?: string
}

export type UPlotCanvasProps = {
  /** Source x axis in ppm. Float32Array preferred — uPlot consumes typed arrays. */
  x: number[] | Float32Array
  /** Observed intensity values matching ``x`` element-for-element. */
  y: number[] | Float32Array
  /** Optional predicted overlay (separate x/y arrays). */
  predictedX?: number[] | Float32Array
  predictedY?: number[] | Float32Array
  predictedLabel?: string
  /** Optional peak markers — rendered as a points-only series. */
  peaks?: UPlotPeak[]
  showPeaks?: boolean
  showPredicted?: boolean
  reversedXAxis?: boolean
  xLabel?: string
  yLabel?: string
  /** Active x-axis window; ``null`` = autorange. */
  xRange?: [number, number] | null
  /** Active y-axis upper bound. */
  yMax?: number
  /** "zoom" → drag box-zooms x. "pan" → drag pans x without zooming. */
  dragMode?: "zoom" | "pan"
  /** Called when the user releases a zoom/pan with the new x range. */
  onXRangeChange?: (range: [number, number] | null) => void
  /** Render height (px). */
  height?: number
}

type AlignedSeriesValue = readonly (number | null)[] | number[] | Float32Array | null

function toUplotSeries(values: AlignedSeriesValue | undefined): number[] | Float32Array | null {
  if (values == null) return null
  if (values instanceof Float32Array) return values
  // uPlot accepts null at element level (renders as a gap) but its TS types
  // declare ``number[]``; cast through unknown so we stay typesafe at the
  // boundary while preserving the gap semantics at runtime.
  return values as unknown as number[]
}

const palette = {
  observed: "#2563eb",
  predicted: "#c026d3",
  peak: "#ea580c",
  axis: "#6b7280",
  grid: "rgba(107, 114, 128, 0.18)",
}

function isMonotonicAsc(values: number[] | Float32Array): boolean {
  for (let i = 1; i < values.length; i++) {
    if (values[i] < values[i - 1]) return false
  }
  return true
}

/**
 * Co-sort x with one or more y-series so the x array is monotonically
 * increasing. uPlot REQUIRES this — Plotly's scattergl did not. Skipping the
 * sort is what was previously producing a blank chart for unsorted spectrum
 * payloads (e.g. peak-table CSV inputs whose rows are in file order rather
 * than shift order).
 */
function sortByXAscending(
  x: number[] | Float32Array,
  ys: ((number | null)[] | number[] | Float32Array | null)[],
): {
  x: number[]
  ys: ((number | null)[] | null)[]
} {
  const n = x.length
  const indices = new Array<number>(n)
  for (let i = 0; i < n; i++) indices[i] = i
  indices.sort((a, b) => x[a] - x[b])
  const sortedX = new Array<number>(n)
  for (let i = 0; i < n; i++) sortedX[i] = x[indices[i]]
  const sortedYs: ((number | null)[] | null)[] = ys.map((series) => {
    if (series == null) return null
    const out: (number | null)[] = new Array(n)
    for (let i = 0; i < n; i++) {
      const v = (series as { [k: number]: number | null })[indices[i]]
      out[i] = v == null ? null : v
    }
    return out
  })
  return { x: sortedX, ys: sortedYs }
}

function toAligned(
  x: number[] | Float32Array,
  y: number[] | Float32Array,
  predictedY: (number | null)[] | null,
  peakY: (number | null)[] | null,
): AlignedData {
  // uPlot requires every series to have the same length as the x array. If
  // an overlay/peaks series is absent we pad with all-null entries so the
  // series index stays stable but the trace renders as fully transparent
  // (uPlot's ``accScale`` skips null samples but throws on a series-level
  // null reference — that's the root cause of the "Cannot read properties
  // of null" crash we saw at runtime).
  const len = x.length
  const predicted: (number | null)[] = predictedY ?? new Array(len).fill(null)
  const peak: (number | null)[] = peakY ?? new Array(len).fill(null)

  // Sort x ascending if needed. Without this uPlot silently fails to render
  // the line for unsorted inputs.
  if (!isMonotonicAsc(x)) {
    const sorted = sortByXAscending(x, [y, predicted, peak])
    return [
      sorted.x,
      toUplotSeries(sorted.ys[0]) as number[],
      toUplotSeries(sorted.ys[1]) as number[],
      toUplotSeries(sorted.ys[2]) as number[],
    ] as AlignedData
  }
  return [
    toUplotSeries(x) as number[],
    toUplotSeries(y) as number[],
    toUplotSeries(predicted) as number[],
    toUplotSeries(peak) as number[],
  ] as AlignedData
}

function alignPeaksToX(
  x: number[] | Float32Array,
  peaks: UPlotPeak[] | undefined,
): (number | null)[] | null {
  if (!peaks || peaks.length === 0) return null
  const result: (number | null)[] = new Array(x.length).fill(null)
  if (x.length === 0) return result
  // Sort peaks once; binary-search each into x for ~O(p log n).
  const sorted = [...peaks].sort((a, b) => a.ppm - b.ppm)
  for (const peak of sorted) {
    let lo = 0
    let hi = x.length - 1
    while (lo < hi) {
      const mid = (lo + hi) >> 1
      if (x[mid] < peak.ppm) lo = mid + 1
      else hi = mid
    }
    // Bracket the insertion point: pick the nearest of lo, lo-1.
    let idx = lo
    if (idx > 0 && Math.abs(x[idx - 1] - peak.ppm) < Math.abs(x[idx] - peak.ppm)) {
      idx = idx - 1
    }
    result[idx] = peak.intensity ?? null
  }
  return result
}

export const UPlotCanvas = memo(function UPlotCanvas({
  x,
  y,
  predictedX,
  predictedY,
  predictedLabel,
  peaks,
  showPeaks = true,
  showPredicted = true,
  reversedXAxis = true,
  xLabel = "ppm",
  yLabel = "Intensity",
  xRange = null,
  yMax,
  dragMode = "zoom",
  onXRangeChange,
  height = 480,
}: UPlotCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const plotRef = useRef<uPlotType | null>(null)

  // Resample predicted onto the observed x axis when an overlay is present.
  const predictedAligned = useMemo<(number | null)[] | null>(() => {
    if (!showPredicted || !predictedX || !predictedY) return null
    if (predictedX.length === 0 || predictedY.length === 0) return null
    // Lightweight nearest-x re-sampler. Same-length overlays pass through
    // untouched; otherwise we project each predicted point onto the closest
    // observed x bin.
    if (predictedX.length === x.length) {
      // Best case: same axis. Replace null gaps with NaN so uPlot renders.
      return Array.from(predictedY, (v) => (Number.isFinite(v) ? v : null))
    }
    const aligned: (number | null)[] = new Array(x.length).fill(null)
    // Build sorted lookup of predicted (ppm → intensity) for binary search.
    const pairs: Array<[number, number]> = []
    for (let i = 0; i < predictedX.length; i++) {
      const px = predictedX[i]
      const py = predictedY[i]
      if (Number.isFinite(px) && Number.isFinite(py)) pairs.push([px, py])
    }
    pairs.sort((a, b) => a[0] - b[0])
    for (let i = 0; i < x.length; i++) {
      const target = x[i]
      let lo = 0
      let hi = pairs.length - 1
      while (lo < hi) {
        const mid = (lo + hi) >> 1
        if (pairs[mid][0] < target) lo = mid + 1
        else hi = mid
      }
      const best =
        lo > 0 && Math.abs(pairs[lo - 1][0] - target) < Math.abs(pairs[lo][0] - target)
          ? pairs[lo - 1]
          : pairs[lo]
      if (best && Math.abs(best[0] - target) <= 0.5) {
        aligned[i] = best[1]
      }
    }
    return aligned
  }, [predictedX, predictedY, showPredicted, x])

  const peakAligned = useMemo<(number | null)[] | null>(
    () => (showPeaks ? alignPeaksToX(x, peaks) : null),
    [x, peaks, showPeaks],
  )

  // Options are recomputed only when the things that genuinely change the
  // layout change. The data array (which changes constantly during gain
  // adjustments) is shipped via setData, not by recreating options.
  const optionsKey = useMemo(
    () =>
      JSON.stringify({
        height,
        reversedXAxis,
        xLabel,
        yLabel,
        dragMode,
        showPredicted: Boolean(predictedAligned),
        showPeaks: Boolean(peakAligned),
        yMax,
        xRange,
      }),
    [
      height,
      reversedXAxis,
      xLabel,
      yLabel,
      dragMode,
      predictedAligned,
      peakAligned,
      yMax,
      xRange,
    ],
  )

  // Mount once. uPlot is created lazily on the client.
  // We hold off on the actual ``new uPlot(...)`` call until the container has
  // a non-zero clientWidth — otherwise uPlot stamps a 0-px-wide canvas that
  // doesn't repaint when the ResizeObserver later fires. The plan PDF flags
  // this as the most common source of "spectrum doesn't appear" bugs.
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    let cancelled = false
    let resizeObserver: ResizeObserver | null = null

    const buildChart = (uPlot: UPlotCtor, width: number) => {
      if (cancelled || !containerRef.current || plotRef.current) return
      const initialData = toAligned(x, y, predictedAligned, peakAligned)
      const measuredHeight = containerRef.current.clientHeight || height
      const options: Options = {
        width,
        height: measuredHeight,
        cursor: {
          drag: {
            x: true,
            y: false,
            uni: dragMode === "zoom" ? 50 : 0,
          },
          focus: { prox: 30 },
        },
        scales: {
          x: {
            range: (_u, dmin, dmax) =>
              xRange
                ? reversedXAxis
                  ? [xRange[1], xRange[0]]
                  : [xRange[0], xRange[1]]
                : reversedXAxis
                  ? [dmax, dmin]
                  : [dmin, dmax],
          },
          y: {
            range: (_u, dmin, dmax) => {
              const upper = yMax ?? dmax * 1.05
              return [Math.min(0, dmin), upper > 0 ? upper : 1]
            },
          },
        },
        axes: [
          {
            stroke: palette.axis,
            grid: { stroke: palette.grid, width: 1 },
            ticks: { stroke: palette.axis, width: 1 },
            label: xLabel,
            labelSize: 28,
          },
          {
            stroke: palette.axis,
            grid: { stroke: palette.grid, width: 1 },
            ticks: { stroke: palette.axis, width: 1 },
            label: yLabel,
            labelSize: 28,
            show: false, // NMR convention: hide intensity axis labels.
          },
        ],
        series: [
          {},
          {
            label: "Observed",
            stroke: palette.observed,
            width: 1.25,
            points: { show: false },
            spanGaps: false,
          },
          {
            label: predictedLabel ?? "Predicted",
            stroke: palette.predicted,
            width: 1,
            dash: [6, 4],
            points: { show: false },
            spanGaps: false,
          },
          {
            label: "Peaks",
            stroke: palette.peak,
            width: 0,
            points: {
              show: true,
              size: 6,
              stroke: palette.peak,
              fill: palette.peak,
            },
          },
        ],
        hooks: {
          setScale: [
            (u, key) => {
              if (key !== "x" || !onXRangeChange) return
              const scale = u.scales.x
              if (scale.min == null || scale.max == null) return
              const lo = Math.min(scale.min, scale.max)
              const hi = Math.max(scale.min, scale.max)
              onXRangeChange([lo, hi])
            },
          ],
        },
        legend: { show: false },
      }
      plotRef.current = new uPlot(options, initialData, container)
    }

    // Promise + width gate. We may need to wait for the ResizeObserver to
    // fire before we have a positive clientWidth.
    let uPlotCtor: UPlotCtor | null = null
    const tryMount = () => {
      if (!uPlotCtor || !containerRef.current) return
      const width = containerRef.current.clientWidth
      if (width <= 0) return // wait for ResizeObserver
      buildChart(uPlotCtor, width)
    }

    loadUPlot().then((u) => {
      if (cancelled) return
      uPlotCtor = u
      tryMount()
    })

    // Resize the canvas via rafThrottle so a burst of layout events
    // collapses into a single setSize() per frame. We also lean on the
    // observer to trigger the very first mount once the container has
    // measurable width.
    const handleResize = rafThrottle((width: number, h: number) => {
      if (width <= 0) return
      if (!plotRef.current) {
        tryMount()
        return
      }
      plotRef.current.setSize({ width, height: h || height })
    })
    resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return
      const measuredWidth = entry.contentRect.width || container.clientWidth
      const measuredHeight = entry.contentRect.height || container.clientHeight
      handleResize(measuredWidth, measuredHeight)
    })
    resizeObserver.observe(container)

    // First-render fallback — if width is already positive, attempt mount
    // straight away (don't wait for the next animation frame).
    queueMicrotask(() => tryMount())

    // Belt-and-suspenders: in some layouts (sticky parent with deferred
    // measurement) neither queueMicrotask nor ResizeObserver fires before
    // React's next commit. Try again on the next two animation frames.
    const raf1 = requestAnimationFrame(() => tryMount())
    let raf2: number | null = null
    raf2 = requestAnimationFrame(() => tryMount())

    return () => {
      cancelled = true
      if (raf1) cancelAnimationFrame(raf1)
      if (raf2) cancelAnimationFrame(raf2)
      resizeObserver?.disconnect()
      plotRef.current?.destroy()
      plotRef.current = null
    }
    // ``optionsKey`` includes every layout-affecting prop so when one
    // changes we tear the chart down and rebuild — far rarer than data
    // updates, so the hit is acceptable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [optionsKey])

  // Data updates: setData is constant-time and reuses the existing canvas.
  useEffect(() => {
    const plot = plotRef.current
    if (!plot) return
    const aligned = toAligned(x, y, predictedAligned, peakAligned)
    plot.setData(aligned)
  }, [x, y, predictedAligned, peakAligned])

  return (
    <div
      ref={containerRef}
      data-testid="uplot-spectrum-canvas"
      // height={height} as the minimum, but allow the parent to stretch the
      // container so the chart fills the sticky SpectrumViewer area instead
      // of leaving a band of empty space.
      style={{ width: "100%", height: "100%", minHeight: height }}
    />
  )
})

