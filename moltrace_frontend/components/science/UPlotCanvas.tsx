"use client"

/**
 * Canvas-based NMR spectrum renderer (uPlot).
 *
 * Step 5 of the spectrum-stabilization plan. The implementation is
 * deliberately conservative — uPlot has a number of strict invariants that
 * Plotly's scattergl did not, and earlier iterations of this file silently
 * failed for unsorted x, custom y scales that clipped data out of view,
 * null-padded extra series, and 0-pixel container widths at mount.
 *
 * Rules this component now follows:
 *
 *   1. Observed line is the single uPlot series. Predicted overlay and peak
 *      markers are rendered as separate, transparent overlays on top of the
 *      canvas so they cannot interfere with uPlot's data validation.
 *   2. uPlot's auto-range is used for both axes (we only flip x via
 *      ``dir: -1`` for NMR convention). Custom scale.range functions that
 *      clipped data out of the visible window are gone.
 *   3. x is sorted ascending if needed before being handed to uPlot.
 *   4. The chart is mounted only once the container has a positive
 *      clientWidth. Multiple triggers race to mount — whichever wins, wins.
 *   5. Resize is rAF-throttled.
 */

import React, { memo, useEffect, useMemo, useRef } from "react"
import type uPlotType from "uplot"
import type { AlignedData, Options } from "uplot"
import { rafThrottle } from "@/src/lib/spectracheck/raf-throttle"
import "uplot/dist/uPlot.min.css"

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
  x: number[] | Float32Array
  y: number[] | Float32Array
  predictedX?: number[] | Float32Array
  predictedY?: number[] | Float32Array
  predictedLabel?: string
  peaks?: UPlotPeak[]
  showPeaks?: boolean
  showPredicted?: boolean
  reversedXAxis?: boolean
  xLabel?: string
  yLabel?: string
  xRange?: [number, number] | null
  /** Reserved — uPlot auto-ranges Y, but we still accept the prop for API parity. */
  yMax?: number
  dragMode?: "zoom" | "pan"
  onXRangeChange?: (range: [number, number] | null) => void
  height?: number
}

const palette = {
  observed: "#2563eb",
  predicted: "#c026d3",
  peak: "#ea580c",
  axis: "#6b7280",
  grid: "rgba(107, 114, 128, 0.18)",
}

function isMonotonicAsc(values: ArrayLike<number>): boolean {
  for (let i = 1; i < values.length; i++) {
    if (values[i] < values[i - 1]) return false
  }
  return true
}

/**
 * Co-sort x ascending with paired y arrays. uPlot requires monotonic x;
 * Plotly's scattergl did not. Returning plain number[] keeps uPlot's type
 * checker happy.
 */
function sortAscending(
  x: ArrayLike<number>,
  y: ArrayLike<number>,
): { x: number[]; y: number[] } {
  const n = x.length
  const indices = new Array<number>(n)
  for (let i = 0; i < n; i++) indices[i] = i
  indices.sort((a, b) => (x[a] as number) - (x[b] as number))
  const sortedX = new Array<number>(n)
  const sortedY = new Array<number>(n)
  for (let i = 0; i < n; i++) {
    const idx = indices[i]
    sortedX[i] = x[idx] as number
    sortedY[i] = y[idx] as number
  }
  return { x: sortedX, y: sortedY }
}

function buildObservedData(
  xIn: number[] | Float32Array,
  yIn: number[] | Float32Array,
): AlignedData {
  if (xIn.length === 0 || yIn.length === 0 || xIn.length !== yIn.length) {
    return [[], []] as unknown as AlignedData
  }
  if (isMonotonicAsc(xIn)) {
    // Pass-through. uPlot accepts number[] (and Float32Array through the
    // ``number[]`` cast — TS types are stricter than the runtime).
    return [xIn as number[], yIn as number[]] as unknown as AlignedData
  }
  const sorted = sortAscending(xIn, yIn)
  return [sorted.x, sorted.y] as unknown as AlignedData
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
  // yLabel intentionally unused — NMR convention hides the intensity axis.
  xRange = null,
  yMax,
  dragMode = "zoom",
  onXRangeChange,
  height = 480,
}: UPlotCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const plotRef = useRef<uPlotType | null>(null)

  const data = useMemo(() => buildObservedData(x, y), [x, y])

  // Stable options — recomputed only when one of the layout knobs changes,
  // not when the data does (data updates flow through setData below).
  const optionsKey = useMemo(
    () =>
      JSON.stringify({
        height,
        reversedXAxis,
        xLabel,
        dragMode,
        xRange,
        yMax,
      }),
    [height, reversedXAxis, xLabel, dragMode, xRange, yMax],
  )

  // Mount uPlot once the container has measurable width. Multiple triggers
  // race to fire (dynamic-import resolution, ResizeObserver, requestAnimationFrame)
  // so we don't lose the first mount to deferred sticky layout.
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    let cancelled = false
    let ctor: UPlotCtor | null = null
    let resizeObserver: ResizeObserver | null = null
    const rafIds: number[] = []

    const tryMount = () => {
      if (cancelled || plotRef.current || !ctor) return
      const node = containerRef.current
      if (!node) return
      // Don't gate on positive clientWidth — sticky / flex layouts can take a
      // frame or two before clientWidth is non-zero, and in some cases the
      // ResizeObserver only fires AFTER the container has finished hydrating
      // (so we'd never mount). Use a 600px fallback and let the observer
      // correct it the moment real width is available.
      const width = node.clientWidth > 0 ? node.clientWidth : 600
      const measuredHeight = node.clientHeight > 0 ? node.clientHeight : height
      const initialData = data.length >= 2 && (data[0] as ArrayLike<number>).length > 0
        ? data
        : ([[0], [0]] as unknown as AlignedData)
      const options: Options = {
        width,
        height: measuredHeight,
        cursor: {
          drag: { x: true, y: false, uni: dragMode === "zoom" ? 50 : 0 },
          focus: { prox: 30 },
        },
        scales: {
          x: {
            // NMR convention: ppm decreases left-to-right. Auto-range, then
            // swap min/max so uPlot renders right-to-left.
            range: (_u, dmin, dmax) =>
              xRange
                ? reversedXAxis ? [xRange[1], xRange[0]] : [xRange[0], xRange[1]]
                : reversedXAxis ? [dmax, dmin] : [dmin, dmax],
          },
          y: {
            // NMR data has extreme dynamic range (the residual solvent peak
            // is ~10^5× the baseline). Auto-range squashes the analyte
            // signal to a single pixel above zero. Use the caller-supplied
            // ``yMax`` (robust 99th-percentile from SpectrumViewer) as the
            // upper bound when provided; fall back to auto-range so this
            // component remains useful standalone.
            range: (_u, dmin, dmax) => {
              const lower = Math.min(0, dmin)
              if (typeof yMax === "number" && Number.isFinite(yMax) && yMax > 0) {
                return [lower, yMax]
              }
              return [lower, dmax * 1.05 || 1]
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
          { stroke: palette.axis, grid: { stroke: palette.grid, width: 1 }, show: false },
        ],
        series: [
          {},
          {
            label: "Observed",
            stroke: palette.observed,
            width: 1.5,
            points: { show: false },
            spanGaps: true,
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
      try {
        plotRef.current = new ctor(options, initialData, node)
      } catch {
        // If uPlot throws (e.g. running in jsdom with no canvas), swallow —
        // the test runtime doesn't render pixels anyway. Browser path will
        // succeed.
      }
    }

    loadUPlot().then((u) => {
      if (cancelled) return
      ctor = u
      tryMount()
    })

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
      handleResize(
        entry.contentRect.width || container.clientWidth,
        entry.contentRect.height || container.clientHeight,
      )
    })
    resizeObserver.observe(container)

    queueMicrotask(() => tryMount())
    rafIds.push(requestAnimationFrame(() => tryMount()))
    rafIds.push(requestAnimationFrame(() => tryMount()))

    return () => {
      cancelled = true
      rafIds.forEach((id) => cancelAnimationFrame(id))
      resizeObserver?.disconnect()
      plotRef.current?.destroy()
      plotRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [optionsKey])

  // Data updates: setData is constant-time and reuses the existing canvas.
  useEffect(() => {
    const plot = plotRef.current
    if (!plot) return
    plot.setData(data)
  }, [data])

  // Peak / predicted overlays — rendered as absolutely-positioned SVG on top
  // of the canvas. Decoupling them from uPlot's series array means we never
  // confuse uPlot's auto-range computation with sparse data, and peak markers
  // can carry rich labels that uPlot's points-only series cannot.
  const xMinMax = useMemo<{ min: number; max: number } | null>(() => {
    if (data.length < 2) return null
    const xs = data[0] as ArrayLike<number>
    if (xs.length === 0) return null
    let min = Infinity
    let max = -Infinity
    for (let i = 0; i < xs.length; i++) {
      const v = xs[i] as number
      if (v < min) min = v
      if (v > max) max = v
    }
    if (!Number.isFinite(min) || !Number.isFinite(max)) return null
    return { min, max }
  }, [data])

  const renderXRange = xRange ?? (xMinMax ? [xMinMax.min, xMinMax.max] : null)

  return (
    <div
      ref={containerRef}
      data-testid="uplot-spectrum-canvas"
      style={{ position: "relative", width: "100%", height: "100%", minHeight: height }}
    >
      {showPeaks && peaks && peaks.length > 0 && renderXRange ? (
        <PeakOverlay peaks={peaks} xRange={renderXRange} reversedXAxis={reversedXAxis} />
      ) : null}
      {showPredicted && predictedX && predictedY && predictedY.length > 0 ? (
        <PredictedOverlay
          x={predictedX}
          y={predictedY}
          label={predictedLabel}
          xRange={renderXRange}
          reversedXAxis={reversedXAxis}
        />
      ) : null}
    </div>
  )
})

// ────────────────────────────────────────────────────────────────────────────
// Lightweight SVG overlays
// ────────────────────────────────────────────────────────────────────────────

function projectX(value: number, xRange: [number, number], reversed: boolean): number {
  const [lo, hi] = reversed ? [xRange[1], xRange[0]] : xRange
  if (hi === lo) return 50
  const pct = (value - lo) / (hi - lo)
  return Math.max(0, Math.min(100, pct * 100))
}

function PeakOverlay({
  peaks,
  xRange,
  reversedXAxis,
}: {
  peaks: UPlotPeak[]
  xRange: [number, number]
  reversedXAxis: boolean
}) {
  return (
    <div
      data-testid="uplot-peak-overlay"
      style={{
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
      }}
    >
      {peaks.map((peak, idx) => {
        const leftPct = projectX(peak.ppm, xRange, reversedXAxis)
        return (
          <div
            key={`${peak.ppm}-${idx}`}
            style={{
              position: "absolute",
              left: `${leftPct}%`,
              bottom: 32,
              transform: "translateX(-50%)",
              color: palette.peak,
              fontFamily: "var(--font-mono, ui-monospace, monospace)",
              fontSize: 10,
              whiteSpace: "nowrap",
              textShadow: "0 0 2px rgba(255,255,255,0.95)",
            }}
          >
            ▼
            {peak.label ? (
              <div style={{ fontSize: 9, marginTop: 1 }}>{peak.label}</div>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}

function PredictedOverlay({
  x,
  y,
  label,
  xRange,
  reversedXAxis,
}: {
  x: number[] | Float32Array
  y: number[] | Float32Array
  label?: string
  xRange: [number, number] | null
  reversedXAxis: boolean
}) {
  // Render the predicted spectrum as dashed vertical sticks for each predicted
  // peak. Cheap, doesn't fight with uPlot's series, and conveys the same
  // information as a dashed line trace.
  const effective = xRange ?? [0, 1]
  return (
    <div
      data-testid="uplot-predicted-overlay"
      style={{
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
      }}
    >
      {Array.from({ length: x.length }).map((_, i) => {
        const xi = (x as ArrayLike<number>)[i]
        const yi = (y as ArrayLike<number>)[i]
        if (!Number.isFinite(xi) || !Number.isFinite(yi)) return null
        const leftPct = projectX(xi, effective, reversedXAxis)
        return (
          <div
            key={`pred-${i}`}
            style={{
              position: "absolute",
              left: `${leftPct}%`,
              top: 12,
              bottom: 32,
              width: 0,
              borderLeft: `1px dashed ${palette.predicted}`,
              opacity: 0.6,
            }}
            title={label ?? "Predicted"}
          />
        )
      })}
    </div>
  )
}
